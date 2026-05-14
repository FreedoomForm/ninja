/**
 * AI Chat Completions API Route
 * Proxies requests to GLM via z-ai-web-dev-sdk
 * OpenAI-compatible API for the Ninja Userbot
 */

import { NextRequest, NextResponse } from 'next/server';
import ZAI from 'z-ai-web-dev-sdk';

// Initialize ZAI instance
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
    const { messages, model = 'glm-4', temperature = 0.7, max_tokens = 2000, stream = false } = body;

    if (!messages || !Array.isArray(messages)) {
      return NextResponse.json(
        { error: 'Messages array is required' },
        { status: 400 }
      );
    }

    const zai = await getZai();

    // Map model names if needed
    const modelMap: Record<string, string> = {
      'glm-4': 'glm-4',
      'glm-4-plus': 'glm-4-plus',
      'glm-4-flash': 'glm-4-flash',
      'gpt-4': 'glm-4',
      'gpt-3.5-turbo': 'glm-4-flash',
    };
    
    const actualModel = modelMap[model] || model;

    // Call GLM via z-ai-web-dev-sdk
    const completion = await zai.chat.completions.create({
      messages: messages.map((msg: { role: string; content: string }) => ({
        role: msg.role as 'system' | 'user' | 'assistant',
        content: msg.content,
      })),
      model: actualModel,
      temperature: temperature,
      max_tokens: max_tokens,
    });

    // Return OpenAI-compatible response
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
    console.error('AI API Error:', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    service: 'Ninja AI Proxy',
    model: 'glm-4',
    endpoints: {
      'POST /api/ai': 'Chat completions (OpenAI-compatible)',
      'POST /api/ai/vision': 'Vision API for image analysis',
    },
  });
}
