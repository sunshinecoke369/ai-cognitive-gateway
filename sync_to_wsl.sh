#!/bin/bash
# AI Cognitive Gateway — WSL 同步脚本
# 将 L 盘（源码真实来源）的改动同步到 WSL 运行环境
# 使用方法: bash sync_to_wsl.sh

set -euo pipefail

L_DRIVE="/mnt/l/AI Cognitive Operating System/ai-cognitive-gateway"
WSL_DIR="/root/ai-cognitive-gateway"

echo "=========================================="
echo "  AI Cognitive Gateway — WSL Sync"
echo "=========================================="
echo "  源目录: ${L_DRIVE}"
echo "  目标目录: ${WSL_DIR}"
echo "=========================================="

# 检查源目录
if [ ! -d "${L_DRIVE}" ]; then
    echo "[ERROR] 源目录不存在: ${L_DRIVE}"
    echo "请检查 L 盘是否已挂载 (ls /mnt/l/)"
    exit 1
fi

# 检查目标目录
if [ ! -d "${WSL_DIR}" ]; then
    echo "[ERROR] 目标目录不存在: ${WSL_DIR}"
    exit 1
fi

# 使用 rsync 同步（排除虚拟环境、缓存、运行时数据）
rsync -av --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='.git/' \
    --exclude='.env' \
    "${L_DRIVE}/" "${WSL_DIR}/"

echo ""
echo "=========================================="
echo "  ✅ 同步完成！"
echo "  请执行: sudo systemctl restart ai-gateway"
echo "=========================================="
