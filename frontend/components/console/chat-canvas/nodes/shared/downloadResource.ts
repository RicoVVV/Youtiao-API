/**
 * 下载资源（dataURL / http URL）
 * @param url      资源地址
 * @param filename 下载文件名
 */
export function downloadResource(url: string, filename: string) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
