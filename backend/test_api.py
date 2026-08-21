"""Quick test script to verify the API is working"""
import httpx
import asyncio

async def test_api():
    async with httpx.AsyncClient() as client:
        # Test /healthz endpoint
        response = await client.get("http://localhost:8000/healthz")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "SmartCarpoolingApp"
        
        print("\n✅ /healthz endpoint test PASSED!")
        
        # Test root endpoint
        response = await client.get("http://localhost:8000/")
        print(f"\nRoot Status Code: {response.status_code}")
        print(f"Root Response: {response.json()}")
        
        print("\n✅ Root endpoint test PASSED!")
        
        # Test docs
        response = await client.get("http://localhost:8000/docs")
        print(f"\nDocs Status Code: {response.status_code}")
        print("\n✅ Swagger docs are accessible!")

if __name__ == "__main__":
    asyncio.run(test_api())
