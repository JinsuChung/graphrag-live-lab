#!/bin/bash
# GraphRAG 라이브 랩 실행
#   macOS: Finder 에서 더블클릭 / 터미널에서 ./start.command
#   Linux: ./start.command
#   Windows: .venv\Scripts\python app\server.py
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo ".venv 가 없습니다. README 의 '설치' 단계를 먼저 실행하세요."
  read -r -p "엔터를 누르면 종료합니다." _
  exit 1
fi
PORT="${PORT:-8000}"
open_browser() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1
  fi
}
if (command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1); then
  echo "포트 $PORT 가 이미 사용 중입니다. 이미 실행 중이면 브라우저만 엽니다."
  open_browser "http://localhost:$PORT"
  exit 0
fi
(sleep 4; open_browser "http://localhost:$PORT") &
echo "종료하려면 이 창에서 Ctrl+C 를 누르세요."
PORT="$PORT" .venv/bin/python app/server.py
