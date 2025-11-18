import os
import asyncio

from fastapi import FastAPI
import uvicorn

import main as bot_module  # импортируем твой бот как модуль

app = FastAPI()


@app.get("/")
async def root():
    return {"status": "ok", "message": "SAT Kyrgyz bot is running"}


async def start_bot():
    # запускаем твоего бота
    await bot_module.main()


async def main():
    # параллельно запускаем бота и HTTP-сервер
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())

    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
