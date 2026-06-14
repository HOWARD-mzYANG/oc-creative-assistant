import argparse

import uvicorn

from app.main import app


# PyInstaller 打包后的后端入口也使用这组参数；Electron 主进程会传入 host/port。
def parse_args() -> argparse.Namespace:
    """解析后端启动参数。

    返回：
        仅包含 host 和 port 的命令行参数对象。
    """
    parser = argparse.ArgumentParser(description="运行 OC 创意助手后端。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    return parser.parse_args()


def main() -> None:
    """根据命令行参数启动 uvicorn 服务。"""
    args = parse_args()
    # 桌面应用的进程生命周期由 Electron 管理；打包模式下禁用 reload。
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
