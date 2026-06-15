import { NextRequest, NextResponse } from "next/server";
import { runAutoPipeline, getPipelineLogs } from "@/lib/auto-pipeline";

export async function GET() {
  const logs = getPipelineLogs();
  return NextResponse.json({
    status: "ready",
    totalRuns: logs.length,
    recentLogs: logs.slice(0, 20),
    endpoints: {
      trigger: "POST /api/pipeline (启动自动变现管道)",
      status: "GET /api/pipeline (查看运行日志)",
    },
  });
}

export async function POST() {
  try {
    const result = await runAutoPipeline();
    return NextResponse.json({
      success: true,
      collected: result.collected,
      triggered: result.triggered,
      message: `采集${result.collected}条信号，${result.triggered}条触发OSCAR调研`,
      recentLogs: result.logs,
    });
  } catch (error) {
    return NextResponse.json(
      { error: `管道运行失败: ${String(error)}` },
      { status: 500 }
    );
  }
}
