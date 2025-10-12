from datetime import datetime
import tempfile
from io import BytesIO
import os
import re
import pandas as pd
from playwright.async_api import async_playwright
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.trends import TrendItem, VolumePoint, TrendStatus
from app.services.gemini_service import GeminiClient
import warnings



class TrendsScraper:
    def __init__(self, db: AsyncSession):
        """
        db: AsyncSession
        gemini_client: instance of Gemini AI client with a categorize() method
        """
        self.db = db
        self.gemini = GeminiClient()

    async def fetch_trending_csv_bytes(
        self,
        geo: str = "IN",
        hours: str = "168",
        sts: str = "",
    ) -> bytes:
        try:
            """Fetch trending CSV from Google Trends and return CSV content as bytes."""
            url = f"https://trends.google.com/trending?geo={geo}&hours={hours}&status={sts}"
    
            if sts == 'active':
                url = f"https://trends.google.com/trending?geo={geo}&hours={hours}&status=active"
            else:
                url = f"https://trends.google.com/trending?geo={geo}&hours={hours}"
    
            print(f"Fetching trends from URL: {url}")
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
                print(f"downloaded csv")
    
                # Step 5: Trigger download and save to temp file
                async with page.expect_download() as download_info:
                    await download_button.click(force=True)
    
                download = await download_info.value

                print(f"csv in temp file")
                # Step 6: Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                    tmp_path = tmp_file.name
                await download.save_as(tmp_path)
    
                # Step 7: Read bytes from temp file
                with open(tmp_path, "rb") as f:
                    csv_bytes = f.read()

                print(f"bytes read from temp file")
                # Step 8: Delete temp file
                os.remove(tmp_path)
    
                # Step 9: Close browser
                await browser.close()
                print(f"calling function to save csv bytes")
                result = await self.save_csv_bytes(csv_bytes)
            return {"result":result, "geo":geo, "hours":hours,"status":True}

        except Exception as e:
            return {"status": False, "error": str(e), "geo":geo, "hours":hours}

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

    async def save_csv_bytes(self, csv_bytes: bytes, batch_size: int = 10) -> dict:
        try:
            print(f"called function to save csv bytes")
            ts_now = datetime.utcnow()
            df = pd.read_csv(BytesIO(csv_bytes))
            df.columns = [c.strip() for c in df.columns]

            df["search_volume"] = df["Search volume"].fillna("0").apply(self.parse_search_volume)

            # Suppress Pandas warnings for date parsing
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                # Try to parse dates with a common format first
                df["started"] = pd.to_datetime(df["Started"], errors="coerce", utc=True, infer_datetime_format=True)
                df["ended"] = pd.to_datetime(df["Ended"], errors="coerce", utc=True, infer_datetime_format=True)

            df["trend_breakdown"] = df["Trend breakdown"].fillna("").str.strip()
            df["explore_link"] = df["Explore link"]
            df = df[df["search_volume"] > 0]

            inserted_count, updated_count, categorized_count = 0, 0, 0
            to_categorize = []
            trend_map = {}

            print(f"adding in iteration {len(df)}")

            # Step 1: Add/update trends in DB
            for _, row in df.iterrows():
                trend_name = row["Trends"].strip()
                stmt = select(TrendItem).where(TrendItem.trend == trend_name)
                result = await self.db.execute(stmt)
                trend = result.scalar_one_or_none()

                if trend:
                    trend.volume_history.append(VolumePoint(ts=ts_now, value=row["search_volume"]))
                    if len(trend.volume_history) > 20:
                        trend.volume_history = trend.volume_history[-20:]
                    trend.is_growing = len(trend.volume_history) >= 2 and \
                                       trend.volume_history[-1].value > trend.volume_history[-2].value
                    updated_count += 1
                else:
                    trend = TrendItem(
                        trend=trend_name,
                        search_volume=row["search_volume"],
                        started=row["started"].to_pydatetime() if pd.notna(row["started"]) else None,
                        ended=row["ended"].to_pydatetime() if pd.notna(row["ended"]) else None,
                        trend_breakdown=row["trend_breakdown"],
                        explore_link=row["explore_link"],
                        is_growing=False,
                        volume_history=[VolumePoint(ts=ts_now, value=row["search_volume"])],
                        status=TrendStatus.Open,
                    )
                    self.db.add(trend)
                    await self.db.flush()  # get trend.id
                    inserted_count += 1

                if not trend.category:
                    to_categorize.append((trend_name, row["trend_breakdown"]))
                trend_map[trend_name] = trend
            
            print(f"batching categorize function")

            # Step 2: Batch categorize uncategorized trends
            if to_categorize:
                trends, breakdowns = zip(*to_categorize)
                gemini_results = await self.gemini.categorize_batch(list(trends), list(breakdowns))
                for trend_name, cat_dict in zip(trends, gemini_results):
                    trend = trend_map[trend_name]
                    trend.category = cat_dict.get("category")
                    trend.subcategory = cat_dict.get("subcategory")
                    categorized_count += 1

            await self.db.commit()

            print(f"saved to db")

            return {
                "processed_rows": len(df),
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "categorized_count": categorized_count,
            }

        except Exception as e:
            print(f"Error saving CSV bytes: {e}")
            return {"status": False, "error": str(e)}

    async def list_trends(
        self,
        search: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        status: str | None = None,
        is_growing: bool | None = None,
        ongoing: bool | None = None,
        min_volume: int | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "search_volume",
        sort_dir: str = "desc",
    ):
        try:
            """
            Fetch and filter trends from PostgreSQL.
            Filters:
            - category, subcategory
            - is_growing (bool)
            - ongoing (bool): True = not ended yet
            - min_volume (int)
            - search (partial text match)
            - pagination: limit/skip
            """

            stmt = select(TrendItem)

            conditions = []

            # Apply filters dynamically
            if category:
                conditions.append(TrendItem.category.ilike(f"%{category}%"))
            if subcategory:
                conditions.append(TrendItem.subcategory.ilike(f"%{subcategory}%"))
            if is_growing is not None:
                conditions.append(TrendItem.is_growing == is_growing)
            if min_volume is not None:
                conditions.append(TrendItem.search_volume >= min_volume)
            if ongoing is not None:
                # ongoing=True => ended is NULL or ended > now
                now = datetime.utcnow()
                if ongoing:
                    conditions.append(or_(TrendItem.ended.is_(None), TrendItem.ended > now))
                else:
                    conditions.append(and_(TrendItem.ended.is_not(None), TrendItem.ended <= now))
            if search:
                conditions.append(TrendItem.trend.ilike(f"%{search}%"))

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Sorting
            if sort_dir.lower() == "desc":
                stmt = stmt.order_by(desc(getattr(TrendItem, sort_by)))
            else:
                stmt = stmt.order_by(getattr(TrendItem, sort_by))

            # Pagination
            stmt = stmt.offset(offset).limit(limit)

            # Execute
            result = await self.db.execute(stmt)
            trends = result.scalars().all()

            # Serialize
            serialized = []
            for t in trends:
                serialized.append({
                    "id": str(t.id),
                    "trend": t.trend,
                    "search_volume": t.search_volume,
                    "started": t.started.isoformat() if t.started else None,
                    "ended": t.ended.isoformat() if t.ended else None,
                    "trend_breakdown": t.trend_breakdown,
                    "explore_link": t.explore_link,
                    "is_growing": t.is_growing,
                    "category": t.category,
                    "subcategory": t.subcategory,
                    "status": t.status.value if hasattr(t.status, "value") else t.status,
                    "last_updated": t.last_updated.isoformat() if t.last_updated else None,
                })

            return {
                "status": True,
                "count": len(serialized),
                "result": serialized,
            }
        except Exception as e:
            return {"status": False, "error": str(e)}