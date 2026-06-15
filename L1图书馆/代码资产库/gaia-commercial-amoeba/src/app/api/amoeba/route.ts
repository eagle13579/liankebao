import { NextRequest, NextResponse } from "next/server";
import { runAmoebaCycle, runAllAmoebas, getDashboard } from "@/lib/amoeba-engine";

export async function GET() {
  const dashboard = await getDashboard();
  return NextResponse.json(dashboard);
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const { departmentId, all } = body;

    if (all) {
      const result = await runAllAmoebas();
      return NextResponse.json({
        success: true,
        type: "全部门",
        departmentsRun: result.results.length,
        results: result.results,
        totalRevenue: result.totalRevenue,
        message: `✅ ${result.results.length}个阿米巴单元完成一轮调研+产出`,
      });
    }

    if (departmentId) {
      const result = await runAmoebaCycle(departmentId);
      return NextResponse.json({
        success: true,
        type: `部门:${result.unit.departmentName}`,
        research: result.research.topic,
        findings: result.research.keyFindings,
        report: result.report.title,
        reportPrice: result.report.price,
        lesson: result.lesson,
        revenue: result.unit.revenue,
        profit: result.unit.profit,
        cycle: result.unit.cycle,
        unit: result.unit,
        message: `✅ ${result.unit.departmentName} 第${result.unit.cycle}轮阿米巴循环完成`,
      });
    }

    // 无参数：返回当前状态
    const dashboard = await getDashboard();
    return NextResponse.json({ dashboard });
  } catch (error) {
    console.error("Amoeba API error:", error);
    return NextResponse.json(
      { error: `阿米巴运行失败: ${String(error)}` },
      { status: 500 }
    );
  }
}
