from sqlalchemy import select


class QueryBuilder:
    def __init__(self, model):
        self.model = model
        self.query = select(model)

    def join(self, *args):
        self.query = self.query.join(*args)
        return self

    def filter(self, *conditions):
        for cond in conditions:
            if cond is not None:
                self.query = self.query.where(cond)
        return self

    def filter_date_range(self, column, start=None, end_exclusive=None):
        if start is not None:
            self.query = self.query.where(column >= start)
        if end_exclusive is not None:
            self.query = self.query.where(column < end_exclusive)
        return self

    def sort(self, *order_by):
        if order_by:
            self.query = self.query.order_by(*order_by)
        return self

    def paginate(self, page: int, size: int):
        offset = (page - 1) * size
        self.query = self.query.offset(offset).limit(size)
        return self

    def with_cte(self, cte):
        self.query = self.query.select_from(cte)
        return self

    def build(self):
        return self.query
