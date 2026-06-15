import { NextResponse } from "next/server";
import { departments } from "@/lib/data";

export async function GET() {
  // 模拟延迟
  await new Promise((r) => setTimeout(r, 100));

  return NextResponse.json({
    departments,
    total: departments.length,
  });
}
