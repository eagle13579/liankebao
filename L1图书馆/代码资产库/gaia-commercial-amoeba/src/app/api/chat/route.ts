import { NextRequest } from "next/server";
import { employees } from "@/lib/data";
import { generateStreamingResponse } from "@/lib/ai-chat-engine";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { departmentId, message, history } = body;

  if (!departmentId || !message) {
    return new Response(JSON.stringify({ error: "缺少必要参数" }), { status: 400 });
  }

  const deptEmployees = employees.filter((e) => e.department === departmentId);
  const responder = deptEmployees.length > 0
    ? deptEmployees[Math.floor(Math.random() * deptEmployees.length)]
    : null;

  const stream = new ReadableStream({
    async start(controller) {
      try {
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify({ type: "meta", employeeId: responder?.id ?? null })}\n\n`)
        );

        const generator = generateStreamingResponse({
          departmentId,
          messageHistory: history ?? [],
          userQuery: message,
        });

        let fullContent = "";
        for await (const chunk of generator) {
          fullContent += chunk;
          controller.enqueue(
            new TextEncoder().encode(`data: ${JSON.stringify({ type: "content", content: chunk })}\n\n`)
          );
        }

        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify({ type: "done", fullContent })}\n\n`)
        );
      } catch (err) {
        controller.enqueue(
          new TextEncoder().encode(`data: ${JSON.stringify({ type: "error", error: String(err) })}\n\n`)
        );
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
