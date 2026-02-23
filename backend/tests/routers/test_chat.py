from unittest.mock import patch


class TestChatHistory:
    def test_empty(self, client):
        r = client.get("/api/v1/chat/history")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_messages(self, client, engine):
        from sqlmodel import Session

        from rippermod_manager.models.chat import ChatMessage

        with Session(engine) as s:
            s.add(ChatMessage(role="user", content="hello"))
            s.add(ChatMessage(role="assistant", content="hi there"))
            s.commit()

        r = client.get("/api/v1/chat/history")
        data = r.json()
        assert len(data) == 2


class TestChat:
    def test_stores_user_message(self, client, engine):
        async def mock_agent(msg, game_name=None):
            yield {"type": "token", "data": {"content": "response"}}

        with patch(
            "rippermod_manager.agents.orchestrator.run_agent",
            side_effect=mock_agent,
        ):
            r = client.post(
                "/api/v1/chat/",
                json={"message": "test message"},
            )
        assert r.status_code == 200

        from sqlmodel import Session, select

        from rippermod_manager.models.chat import ChatMessage

        with Session(engine) as s:
            msgs = s.exec(select(ChatMessage).where(ChatMessage.role == "user")).all()
            assert any(m.content == "test message" for m in msgs)

    def test_sse_content_type(self, client):
        async def mock_agent(msg, game_name=None):
            yield {"type": "token", "data": {"content": "hi"}}

        with patch(
            "rippermod_manager.agents.orchestrator.run_agent",
            side_effect=mock_agent,
        ):
            r = client.post(
                "/api/v1/chat/",
                json={"message": "hello"},
            )
        assert "text/event-stream" in r.headers["content-type"]

    def test_fallback_when_no_agent(self, client):
        with patch(
            "rippermod_manager.agents.orchestrator.run_agent",
            side_effect=ImportError("no agent"),
        ):
            r = client.post(
                "/api/v1/chat/",
                json={"message": "hello"},
            )
        assert r.status_code == 200
