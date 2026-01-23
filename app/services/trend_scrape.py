from datetime import datetime
import tempfile
from io import BytesIO
import os
import re
import pandas as pd
from playwright.async_api import async_playwright
from sqlalchemy import select, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
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
            if sts == "active":
                url = f"https://trends.google.com/trending?geo={geo}&hours={hours}&status=active"
            else:
                url = f"https://trends.google.com/trending?geo={geo}&hours={hours}"
    
            print(f"Fetching trends from URL: {url}")
    
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,  # keep False for debugging
                    args=["--no-sandbox"],
                )
    
                page = await browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
    
                # Step 1: Load page
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")  # 🔧 CHANGED
                await page.wait_for_timeout(2000)
    
                # Step 2: Click Export button (menu button)
                export_button = page.get_by_role("button", name="Export")  # 🔧 CHANGED
                await export_button.wait_for(timeout=20000)               # 🔧 CHANGED
                await export_button.click()
    
                print("Export menu clicked")
    
                # Step 3: Small wait for menu animation
                await page.wait_for_timeout(500)  # 🔧 CHANGED (shorter & intentional)
    
                # Step 4: Locate Download CSV from global menu
                download_button = page.get_by_role("menuitem", name="Download CSV")  # 🔧 CHANGED
                await download_button.wait_for(state="attached", timeout=15000)      # 🔧 CHANGED
    
                print("Download CSV option visible")
    
                # Step 5: Trigger download
                async with page.expect_download(timeout=20000) as download_info:     # 🔧 CHANGED
                    await download_button.click()
    
                download = await download_info.value
                print("CSV downloaded to temp")
    
                # Step 6: Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
                    tmp_path = tmp_file.name
    
                await download.save_as(tmp_path)
    
                # Step 7: Read bytes
                with open(tmp_path, "rb") as f:
                    csv_bytes = f.read()
    
                print("CSV bytes read")
    
                # Step 8: Cleanup
                os.remove(tmp_path)
    
                # Step 9: Close browser
                await browser.close()
    
                print("Saving CSV bytes")
                result = await self.save_csv_bytes(csv_bytes)
    
            return {"result": result, "geo": geo, "hours": hours, "status": True}
    
        except Exception as e:
            print(f"Error fetching trending CSV: {e}")
            return {"status": False, "error": str(e), "geo": geo, "hours": hours}


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
            print("called function to save csv bytes")
            ts_now = datetime.utcnow()

            # ✅ initialize counters at the top so they exist even if error happens early
            inserted_count = 0
            updated_count = 0
            categorized_count = 0

            df = pd.read_csv(BytesIO(csv_bytes))
            df.columns = [c.strip() for c in df.columns]

            df["search_volume"] = (
                df["Search volume"].fillna("0").apply(self.parse_search_volume)
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                df["started"] = pd.to_datetime(df["Started"], errors="coerce", utc=True)
                df["ended"] = pd.to_datetime(df["Ended"], errors="coerce", utc=True)

            df["trend_breakdown"] = df["Trend breakdown"].fillna("").str.strip()
            df["explore_link"] = df["Explore link"]
            df = df[df["search_volume"] > 0]

            processed_rows = len(df)

            print("total rows to process:", processed_rows)  #

            to_categorize = []
            trend_map = {}

            print(f"adding in iteration {len(df)}")

            # Step 1: Add/update trends
            for _, row in df.iterrows():
                trend_name = row["Trends"].strip()
                stmt = select(TrendItem).where(TrendItem.trend == trend_name)
                result = await self.db.execute(stmt)
                trend = result.scalar_one_or_none()

                if trend:
                    trend.search_volume = row["search_volume"]  # update current volume
                    updated_count += 1
                else:
                    trend = TrendItem(
                        trend=trend_name,
                        search_volume=row["search_volume"],
                        started=row["started"].to_pydatetime()
                        if pd.notna(row["started"])
                        else None,
                        ended=row["ended"].to_pydatetime()
                        if pd.notna(row["ended"])
                        else None,
                        trend_breakdown=row["trend_breakdown"],
                        explore_link=row["explore_link"],
                        is_growing=False,
                        status=TrendStatus.Open,
                    )
                    self.db.add(trend)
                    await self.db.flush()  # assign trend.id
                    inserted_count += 1

                trend_map[trend_name] = trend

            # Commit trends first before inserting volume points
            await self.db.commit()

            # Step 2: Insert or update volume_points with upsert
            print("Inserting volume points (upsert)...")
            volume_rows = []
            for trend in trend_map.values():
                volume_rows.append(
                    {
                        "trend_id": trend.id,
                        "ts": ts_now,
                        "value": trend.search_volume,
                    }
                )

            if volume_rows:
                stmt = insert(VolumePoint).values(volume_rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["trend_id", "ts"],
                    set_={"value": stmt.excluded.value},
                )
                await self.db.execute(stmt)
                await self.db.commit()

            print("batching categorize function")

            # Step 3: Categorize uncategorized trends
            uncategorized = [t for t in trend_map.values() if not t.category]
            if uncategorized:
                trends = [t.trend for t in uncategorized]
                breakdowns = [t.trend_breakdown for t in uncategorized]

                gemini_results = await self.gemini.categorize_batch(trends, breakdowns)
                for trend, cat_dict in zip(uncategorized, gemini_results):
                    trend.category = cat_dict.get("category")
                    trend.subcategory = cat_dict.get("subcategory")
                    categorized_count += 1

                await self.db.commit()

            print("saved to db")

            return {
                "processed_rows": processed_rows,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "categorized_count": categorized_count,
            }

        except Exception as e:
            await self.db.rollback()
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
                    conditions.append(
                        or_(TrendItem.ended.is_(None), TrendItem.ended > now)
                    )
                else:
                    conditions.append(
                        and_(TrendItem.ended.is_not(None), TrendItem.ended <= now)
                    )
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
                serialized.append(
                    {
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
                        "status": t.status.value
                        if hasattr(t.status, "value")
                        else t.status,
                        "last_updated": t.last_updated.isoformat()
                        if t.last_updated
                        else None,
                    }
                )

            return {
                "status": True,
                "count": len(serialized),
                "result": serialized,
            }
        except Exception as e:
            return {"status": False, "error": str(e)}
