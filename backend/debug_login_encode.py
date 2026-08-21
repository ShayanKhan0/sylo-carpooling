import asyncio
from fastapi.encoders import jsonable_encoder
from app.db.session import get_db
from app.modules.auth import service
import app.models.wallet  # noqa: F401
import app.models.wallet_transaction  # noqa: F401
import app.modules.payments.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.matching.models  # noqa: F401
import app.modules.verification.models  # noqa: F401


async def main() -> None:
    async for db in get_db():
        result = await service.login_user(db, "passenger@sylo.app", "Test1234!")
        print(jsonable_encoder(result))
        break


if __name__ == "__main__":
    asyncio.run(main())
