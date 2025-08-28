# # In tests/integration/test_rapidapi_rules.py

# from fastapi.testclient import TestClient


# def test_transcribe_rejects_missing_rapidapi_key(
#     test_client: TestClient, synthetic_wav_1s: bytes
# ):
#     """A request without the X-RapidAPI-Key header should be rejected with 401/403."""
#     files = {"file": ("test.wav", synthetic_wav_1s, "audio/wav")}

#     # No RapidAPI headers are sent
#     response = test_client.post("/v1/transcribe", files=files)

#     assert response.status_code in [401, 403]
