from sqlalchemy import func, select


class QueryBuilder:
    def __init__(self, model):
        self.model = model
        self.query = select(model)

    def join(self, *joins):
        for j in joins:
            self.query = self.query.join(*j)
        return self

    def filter(self, *conditions):
        for cond in conditions:
            if cond is not None:
                self.query = self.query.where(cond)
        return self

    def sort(self, sort_fields: list[str]):
        for field in sort_fields:
            desc = field.startswith("-")
            col = getattr(self.model, field.lstrip("-"))
            self.query = self.query.order_by(col.desc() if desc else col.asc())
        return self

    def paginate(self, page: int, limit: int):
        self.query = self.query.offset((page - 1) * limit).limit(limit)
        return self

    def with_cte(self, cte):
        self.query = self.query.select_from(cte)
        return self

    def build(self):
        return self.query
