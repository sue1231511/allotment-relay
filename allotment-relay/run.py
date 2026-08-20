#!/usr/bin/env python3
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8787"))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)
