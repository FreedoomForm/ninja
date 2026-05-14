/**
 * OpenAI-compatible Chat Completions Endpoint
 * Path: /api/chat/completions
 */

import { NextRequest, NextResponse } from 'next/server';
import ZAI from 'z-ai-web-dev-sdk';

let zaiInstance: Awaited<ReturnType<typeof ZAI.create>> | null = null;

async function getZai() {
  if (!zaiInstance) {
    zaiInstance = await ZAI.create();
  }
  return zaiInstance;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, model = 'glm-4', temperature = 0.7, max_tokens = 2000 } = body;

    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: 'Messages array is required' },
        { status: 400 }
      );
    }

    const zai = await getZai();

    const modelMap: Record<string, string> = {
      'glm-4': 'glm-4',
      'glm-4-plus': 'glm-4-plus',
      'glm-4-flash': 'glm-4-flash',
      'gpt-4': 'glm-4',
      'gpt-3.5-turbo': 'glm-4-flash',
    };
    
    const actualModel = modelMap[model] || model;

    const completion = await zai.chat.completions.create({
      messages: messages.map((msg: { role: string; content: string | any[] }) => {
        if (Array.isArray(msg.content)) {
          const textParts = msg.content
            .filter((item: any) => item.type === 'text')
            .map((item: any) => item.text);
          return {
            role: msg.role as 'system' | 'user' | 'assistant',
            content: textParts.join('\n'),
          };
        }
        return {
          role: msg.role as 'system' | 'user' | 'assistant',
          content: String(msg.content),
        };
      }),
      model: actualModel,
      temperature: temperature,
      max_tokens: max_tokens,
    });

    const response = {
      id: `chatcmpl-${Date.now()}`,
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: actualModel,
      choices: [
        {
          index: 0,
          message: {
            role: 'assistant',
            content: completion.choices[0]?.message?.content || '',
          },
          finish_reason: 'stop',
        },
      ],
      usage: {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
      },
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Chat Completions API Error:', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    object: 'list',
    data: [
      { id: 'glm-4', object: 'model', created: Date.now(), owned_by: 'zhipu' },
      { id: 'glm-4-plus', object: 'model', created: Date.now(), owned_by: 'zhipu' },
      { id: 'glm-4-flash', object: 'model', created: Date.now(), owned_by: 'zhipu' },
    ],
  });
}
