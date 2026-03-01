from app.db.supabase import supabase  # Assuming you have a supabase client here

class NicheService:
    async def get_keywords_for_niche(self, niche_name: str):
        # Fetch the niche ID first
        niche = supabase.table("niches").select("id").eq("name", niche_name).single().execute()
        if not niche.data:
            return []
        
        # Fetch all keywords tied to that niche ID
        seeds = supabase.table("niche_seeds").select("keyword").eq("niche_id", niche.data['id']).execute()
        return [item['keyword'] for item in seeds.data]

    async def create_niche(self, name: str, display_name: str):
        return supabase.table("niches").insert({"name": name, "display_name": display_name}).execute()

    async def add_seed_keyword(self, niche_id: str, keyword: str):
        return supabase.table("niche_seeds").insert({"niche_id": niche_id, "keyword": keyword}).execute()