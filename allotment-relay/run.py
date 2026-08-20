#!/usr/bin/env python3
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8787, reload=False)
