"use client";
import { Type, Image, Video, /* Music, */ SlidersHorizontal, Group } from 'lucide-react';

export type AddNodeMenuType = 'textNode' | 'imageNode' | 'videoNode' | 'audioNode' | 'genConfigNode' | 'groupNode';

interface AddNodeMenuProps {
    x: number;
    y: number;
    onSelect: (type: AddNodeMenuType) => void;
    /** 菜单标题，默认「添加节点」；连线落空白处弹出时传「引用该节点生成」 */
    title?: string;
}

const ITEMS: { type: AddNodeMenuType; label: string; icon: React.ReactNode }[] = [
    { type: 'textNode', label: '文本', icon: <Type className="h-4 w-4" /> },
    { type: 'imageNode', label: '图片', icon: <Image className="h-4 w-4" /> },
    { type: 'videoNode', label: '视频', icon: <Video className="h-4 w-4" /> },
    // 音频节点入口暂时隐藏（恢复时同时把 Music 加回导入）
    // { type: 'audioNode', label: '音频', icon: <Music className="h-4 w-4" /> },
    { type: 'genConfigNode', label: '生成配置', icon: <SlidersHorizontal className="h-4 w-4" /> },
    { type: 'groupNode', label: '组', icon: <Group className="h-4 w-4" /> },
];

// 画布添加节点菜单：双击空白处弹出
const AddNodeMenu: React.FC<AddNodeMenuProps> = ({ x, y, onSelect, title = '添加节点' }) => {
    return (
        <div
            className="nodrag absolute z-50 min-w-36 rounded-xl border border-border bg-popover p-1.5 shadow-card"
            style={{ left: x, top: y }}
            onMouseDown={(e) => e.stopPropagation()}
        >
            <div className="px-2 py-1.5 text-xs text-muted-foreground">{title}</div>
            {ITEMS.map(item => (
                <div
                    key={item.type}
                    className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-popover-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                    onClick={() => onSelect(item.type)}
                >
                    <span className="flex h-4 w-4 items-center justify-center text-muted-foreground">
                        {item.icon}
                    </span>
                    <span>{item.label}</span>
                </div>
            ))}
        </div>
    );
};

export default AddNodeMenu;
