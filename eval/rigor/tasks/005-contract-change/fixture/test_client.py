import api
import client

def test_dispatch():
    res = api.dispatch("hello")
    assert res["status"] == "sent"
