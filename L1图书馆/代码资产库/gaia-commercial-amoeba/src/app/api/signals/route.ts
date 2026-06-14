import { NextRequest, NextResponse } from "next/server";
import { scanAllDepartments } from "@/lib/signal-scanner";
import { collectAllRealSignals } from "@/lib/real-signal-sources";

export async function GET(request: NextRequest) {
  const type = request.nextUrl.searchParams.get("type") ?? "status";

  if (type === "scan") {
    const result = await scanAllDepartments();
    return NextResponse.json({
      mode: "ai_simulated",
      success: true,
      totalSignals: result.signals.length,
      hotSignals: result.hotSignals.length,
      signals: result.signals,
      hotList: result.hotSignals,
      summary: result.summary,
    });
  }

  if (type === "real") {
    try {
      const real = await collectAllRealSignals();
      return NextResponse.json({
        mode: "real",
        success: true,
        totalSignals: real.signals.length,
        sourceStats: real.sourceStats,
        signals: real.signals,
      });
    } catch (error) {
      return NextResponse.json(
        { error: `真实采集失败: ${String(error)}` },
        { status: 500 }
      );
    }
  }

  if (type === "hybrid") {
    try {
      const [real, ai] = await Promise.allSettled([
        collectAllRealSignals(),
        scanAllDepartments(),
      ]);

      const realSignals = real.status === "fulfilled" ? real.value.signals : [];
      const aiSignals = ai.status === "fulfilled" ? ai.value.signals : [];

      return NextResponse.json({
        mode: "hybrid",
        success: true,
        stats: {
          real: realSignals.length,
          ai_simulated: aiSignals.length,
          total: realSignals.length + aiSignals.length,
        },
        realSignals,
        aiSignals: aiSignals.slice(0, 10),
      });
    } catch (error) {
      return NextResponse.json(
        { error: `混合采集失败: ${String(error)}` },
        { status: 500 }
      );
    }
  }

  return NextResponse.json({
    status: "ready",
    modes: [
      "?type=scan     - AI模拟扫描（快，全部信源）",
      "?type=real     - 真实采集（GitHub/HN/RSS，标注来源）",
      "?type=hybrid   - 混合模式（真实+AI补充）",
    ],
  });
}
