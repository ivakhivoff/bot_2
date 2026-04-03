from peewee import *

database = SqliteDatabase("db.sqlite3")


class BaseModel(Model):
    class Meta:
        database = database


class Setting(BaseModel):
    chats = TextField()
    texts = TextField()
    counter = IntegerField(default=1)
    by_time = TimeField(default=None, null=True)
    by_counter = IntegerField(default=None, null=True)

    def __repr__(self) -> str:
        return f"<Setting {self.id}>"

    class Meta:
        table_name = "settings"