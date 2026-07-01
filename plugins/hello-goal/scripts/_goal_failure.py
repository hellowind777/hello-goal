#!/usr/bin/env python3
"""hello-goal v2.3.9 StopFailure 守护 —— CC turn 因 API 错误终止时自动恢复继续。

CC v2.1.78+ 在 API 错误（socket 断开/429/503/认证失败等）时触发 StopFailure 事件，
传入 error_type + error_message。本 handler 用 exit code 2 无条件 BLOCK 让任务继续。

使用 exit code 2 而非 JSON stdout —— 与 CC 原生 /goal 评估器并行时不受 JSON 校验影响。
"""
import sys


def main():
    sys.stderr.write("API 错误自动恢复")
    sys.exit(2)


if __name__ == "__main__":
    main()

