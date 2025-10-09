import asyncio
import csv
from datetime import datetime
import tempfile
import os
import io
import re
from dateutil import parser
from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright
from app.db.mongodb import get_mongo_db
from app.db.db_wrapper.mongo_wraper import MongoWrapper
from app.db.models.trends import TrendItem
import pandas as pd
from pymongo import UpdateOne
from io import BytesIO

class TrendsScraper:
    def __init__(self, collection_name: str = "trending_searches"):
        db = get_mongo_db()
        self.collection: AsyncIOMotorCollection = db[collection_name]
        self.mongo = MongoWrapper(self.collection)
        asyncio.create_task(self._ensure_indexes()) # run async index creation

    async def _ensure_indexes(self):
        await self.collection.create_index("trend", unique=True)
        await self.collection.create_index("status")
        await self.collection.create_index("category")
        await self.collection.create_index("subcategory")
        await self.collection.create_index("is_growing", 1),("category",1)
        #await self.collection.create_index("last_updated", expireAfterSeconds=60 * 60 * 24)

    async def fetch_trending_csv_bytes(
        self,
        geo: str = "IN",
        hours: str = "168",
        sts: str = "",
    ) -> bytes:
        """Fetch trending CSV from Google Trends and return CSV content as bytes."""

        if sts == 'active':
            url = f"https://trends.google.com/trending?geo={geo}&hours={hours}&status={sts}"
        else:
            url = f"https://trends.google.com/trending?geo={geo}&hours={hours}"


        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,  # change to False for debugging
                args=["--no-sandbox"],
            )
            page = await browser.new_page(viewport={"width": 1280, "height": 720})

            # Step 1: Load page
            await page.goto(url, timeout=30000, wait_until="networkidle")
            await page.wait_for_timeout(2000)  # ensure JS renders

            # Step 2: Click Export button
            export_button = page.locator(
                'span[jsname="V67aGc"].FOBRw-vQzf8d >> text=Export'
            )
            await export_button.wait_for(state="visible", timeout=15000)
            await export_button.click()

            # Step 3: Wait for dropdown menu to appear
            await page.wait_for_timeout(1000)

            # Step 4: Locate "Download CSV" relative to Export button
            download_button = export_button.locator(
                'xpath=following::span[contains(text(), "Download CSV")]'
            ).first
            await download_button.wait_for(state="visible", timeout=10000)

            # Step 5: Trigger download and save to temp file
            async with page.expect_download() as download_info:
                await download_button.click(force=True)

            download = await download_info.value

            # Step 6: Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                tmp_path = tmp_file.name
            await download.save_as(tmp_path)

            # Step 7: Read bytes from temp file
            with open(tmp_path, "rb") as f:
                csv_bytes = f.read()

            # Step 8: Delete temp file
            os.remove(tmp_path)

            # Step 9: Close browser
            await browser.close()

            result = await self.save_csv_bytes_to_mongo_pandas(csv_bytes)

        return {"result":result, "geo":geo, "hours":hours,"status":True}


    @staticmethod
    def parse_search_volume(volume_str: str) -> int:
        """
        Convert '5M+', '20K+', '1.2M' to numeric integer.
        Returns 0 if unknown or empty.
        """
        if not volume_str:
            return 0
        
        # Remove +, whitespace, commas
        volume_str = volume_str.strip().replace("+", "").replace(",", "")
        
        # Regex to capture numbers with optional K/M suffix
        match = re.match(r"^(\d*\.?\d+)([KMkm]?)$", volume_str)
        if not match:
            return 0
        
        number, suffix = match.groups()
        number = float(number)
        
        if suffix.upper() == "K":
            number *= 1_000
        elif suffix.upper() == "M":
            number *= 1_000_000
        
        return int(number)

    # @staticmethod
    # def parse_datetime(dt_str: str):
    #     """Parse datetime string, handling NaN/None safely."""
    #     if pd.isna(dt_str):  # catches NaN/None
    #         return None
    #     if not isinstance(dt_str, str):  # just in case
    #         return None
    # 
    #     # Replace non-breaking / narrow spaces
    #     dt_str = dt_str.replace("\u202f", " ").replace("\xa0", " ")
    #     try:
    #         return parser.parse(dt_str)
    #     except Exception as e:
    #         print("Failed to parse datetime:", dt_str, e)
    #         return None

    async def save_csv_bytes_to_mongo_pandas(self, csv_bytes: bytes) -> dict:
        """Parse CSV, upsert trends into MongoDB, calculate growth, and apply Gemini categorization."""
        ts_now = datetime.utcnow()

        # Load CSV into DataFrame
        df = pd.read_csv(BytesIO(csv_bytes))
        df.columns = [c.strip() for c in df.columns]

        # Parse search volume & datetime
        df["search_volume"] = df["Search volume"].fillna("0").apply(self.parse_search_volume)
        df["started"] = pd.to_datetime(df["Started"], errors="coerce", utc=True)
        df["ended"] = pd.to_datetime(df["Ended"], errors="coerce", utc=True)
        df["trend_breakdown"] = df["Trend breakdown"].fillna("").str.strip()
        df["explore_link"] = df["Explore link"]

        # Filter zero search volume
        df = df[df["search_volume"] > 0]
        if df.empty:
            return {"processed_rows": 0, "inserted_count": 0, "matched_count": 0, "modified_count": 0, "categorized_count": 0}

        trend_names = df["Trends"].str.strip().unique().tolist()

        # Fetch existing trends
        existing_docs = await self.mongo.collection.find({"trend": {"$in": trend_names}}).to_list(length=None)
        existing_map = {doc["trend"]: doc for doc in existing_docs}

        bulk_ops = []
        uncategorized_trends = []

        for _, row in df.iterrows():
            trend_name = row["Trends"].strip()
            existing_doc = existing_map.get(trend_name)

            # Volume history
            volume_history = existing_doc.get("volume_history", []) if existing_doc else []
            volume_history.append({"ts": ts_now, "value": row["search_volume"]})
            if len(volume_history) > 20:
                volume_history = volume_history[-20:]

            # Determine growth
            is_growing = len(volume_history) >= 2 and volume_history[-1]["value"] > volume_history[-2]["value"]

            trend_doc = {
                "trend": trend_name,
                "search_volume": row["search_volume"],
                "started": row["started"].to_pydatetime() if pd.notna(row["started"]) else None,
                "ended": row["ended"].to_pydatetime() if pd.notna(row["ended"]) else None,
                "trend_breakdown": row["trend_breakdown"],
                "explore_link": row["explore_link"],
                "last_updated": ts_now,
                "volume_history": volume_history,
                "is_growing": is_growing,
                "category": existing_doc.get("category") if existing_doc else None,
                "subcategory": existing_doc.get("subcategory") if existing_doc else None,
                "draft_id": existing_doc.get("draft_id") if existing_doc else None,
                "status": existing_doc.get("status", "Open") if existing_doc else "Open",
            }

            if not trend_doc["category"] and is_growing:
                uncategorized_trends.append(trend_name)

            bulk_ops.append(UpdateOne({"trend": trend_name}, {"$set": trend_doc}, upsert=True))

        # Bulk write trends
        bulk_result = await self.mongo.bulk_write(bulk_ops) if bulk_ops else None

        # Gemini categorization
        categorized_count = 0
        if uncategorized_trends:
            gemini_results = {t: {"category": "Tech", "subcategory": "AI"} for t in uncategorized_trends}
            gemini_bulk_ops = [
                UpdateOne({"trend": t}, {"$set": {"category": cat["category"], "subcategory": cat["subcategory"]}})
                for t, cat in gemini_results.items()
            ]
            if gemini_bulk_ops:
                gemini_result = await self.mongo.bulk_write(gemini_bulk_ops)
                categorized_count = gemini_result.modified_count if gemini_result else 0
        
        return {
            "processed_rows": len(df),
            "inserted_count": bulk_result.upserted_count if bulk_result else 0,
            "matched_count": bulk_result.matched_count if bulk_result else 0,
            "modified_count": bulk_result.modified_count if bulk_result else 0,
            "categorized_count": categorized_count,
        }


    async def list_trends(self):
        filters = {}  # optional filters later
        sort = [("search_volume", -1)]
        limit = 100
        skip = 0

        data = await self.mongo.find(query=filters,sort=sort,limit=limit,skip=skip)

        # Convert _id ObjectId to str to make JSON serializable
        for doc in data:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return {"status":True, "result":data}