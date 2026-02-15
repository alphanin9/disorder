import httpx
import respx

from control_plane.app.adapters.ctfd import CTFdClient, extract_file_entries


def test_ctfd_client_parsing() -> None:
    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.get("https://ctfd.local/api/v1/challenges").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 1, "name": "Warmup", "category": "pwn", "value": 100},
                    ]
                },
            )
        )
        mock_router.get("https://ctfd.local/api/v1/challenges/1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "description": "<p>desc</p>",
                        "files": [{"name": "chal.zip", "url": "/files/chal.zip"}],
                    }
                },
            )
        )
        mock_router.get("https://ctfd.local/files/chal.zip").mock(return_value=httpx.Response(200, content=b"abc"))
        mock_router.post("https://ctfd.local/api/v1/challenges/attempt").mock(
            return_value=httpx.Response(200, json={"data": {"status": "correct"}})
        )

        client = CTFdClient(base_url="https://ctfd.local", api_token="token")
        try:
            challenges = client.list_challenges()
            assert len(challenges) == 1
            assert challenges[0].challenge_id == "1"

            detail = client.get_challenge("1")
            files = extract_file_entries(detail)
            assert files == [{"name": "chal.zip", "url": "/files/chal.zip"}]

            data = client.download_file("/files/chal.zip")
            assert data == b"abc"

            verify = client.submit_flag("1", "flag{demo}")
            assert verify["status"] == "correct"
        finally:
            client.close()
