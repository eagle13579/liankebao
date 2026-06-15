/**
 * 文件库存储层 — 报告/文档的持久化存储
 * JSON文件存储，生产环境替换为数据库
 */
import { promises as fs } from "fs";
import path from "path";

export interface FileItem {
  id: string;
  name: string;
  type: "report" | "document" | "image";
  departmentId: string;
  departmentName: string;
  size: number; // bytes
  createdAt: string;
  downloaded: boolean;
  tags: string[];
  reportId?: string; // 关联报告ID
}

const FILES_DIR = path.join(process.cwd(), "data", "files");

async function ensureDir(): Promise<void> {
  await fs.mkdir(FILES_DIR, { recursive: true });
}

export async function saveFile(file: FileItem): Promise<void> {
  await ensureDir();
  const filePath = path.join(FILES_DIR, `${file.id}.json`);
  await fs.writeFile(filePath, JSON.stringify(file, null, 2), "utf-8");
}

export async function getFile(fileId: string): Promise<FileItem | null> {
  try {
    const filePath = path.join(FILES_DIR, `${fileId}.json`);
    const data = await fs.readFile(filePath, "utf-8");
    return JSON.parse(data);
  } catch {
    return null;
  }
}

export async function listFiles(departmentId?: string): Promise<FileItem[]> {
  await ensureDir();
  const files = await fs.readdir(FILES_DIR);
  const result: FileItem[] = [];

  for (const file of files) {
    if (!file.endsWith(".json")) continue;
    try {
      const data = await fs.readFile(path.join(FILES_DIR, file), "utf-8");
      const item: FileItem = JSON.parse(data);
      if (!departmentId || item.departmentId === departmentId) {
        result.push(item);
      }
    } catch {
      continue;
    }
  }

  // 按时间倒序
  result.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  return result;
}

export async function deleteFile(fileId: string): Promise<boolean> {
  try {
    const filePath = path.join(FILES_DIR, `${fileId}.json`);
    await fs.unlink(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function getFilesCount(departmentId?: string): Promise<number> {
  const files = await listFiles(departmentId);
  return files.length;
}
