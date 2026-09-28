"use client";
import { useEffect, useRef, useState } from 'react';

/** 判定为点击的最大位移（px）：按下→抬起位移超过该值视为拖拽 */
const CLICK_MOVE_TOLERANCE = 6;

/**
 * 节点"点击展开"状态：仅真实点击（非拖拽）时展开节点附属 UI（悬浮操作栏 / 生成区）。
 * - 拖拽会使节点进入 selected，但不算点击，不展开；
 * - 已展开后再拖拽时（dragging）临时隐藏；
 * - 取消选中后复位，下次需重新点击才展开。
 */
export function useNodeClickExpand(selected: boolean | undefined, dragging: boolean | undefined) {
    const [clicked, setClicked] = useState(false);
    const downPosRef = useRef<{ x: number; y: number } | null>(null);

    // 取消选中后复位，下次需重新点击才展开
    useEffect(() => {
        if (!selected) setClicked(false);
    }, [selected]);

    const onPointerDown = (e: React.PointerEvent) => {
        downPosRef.current = { x: e.clientX, y: e.clientY };
    };

    const onPointerUp = (e: React.PointerEvent) => {
        const down = downPosRef.current;
        downPosRef.current = null;
        if (!down) return;
        if (e.shiftKey) return;
        const dx = e.clientX - down.x;
        const dy = e.clientY - down.y;
        if (dx * dx + dy * dy <= CLICK_MOVE_TOLERANCE * CLICK_MOVE_TOLERANCE) setClicked(true);
    };

    return { expanded: Boolean(selected && clicked && !dragging), onPointerDown, onPointerUp };
}
