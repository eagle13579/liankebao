import { NextRequest, NextResponse } from "next/server";
import { employees, getEmployeesByDepartment } from "@/lib/data";

export async function GET(request: NextRequest) {
  await new Promise((r) => setTimeout(r, 50));

  const deptId = request.nextUrl.searchParams.get("department");

  if (deptId) {
    const filtered = getEmployeesByDepartment(deptId);
    return NextResponse.json({
      employees: filtered,
      total: filtered.length,
    });
  }

  return NextResponse.json({
    employees,
    total: employees.length,
  });
}
