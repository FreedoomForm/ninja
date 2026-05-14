/**
 * AI Chat Completions API Route
 * Proxies requests to GLM via z-ai-web-dev-sdk
 * OpenAI-compatible API for the Ninja Userbot
 */

import { NextRequest, NextResponse } from 'next/server';
import ZAI from 'z-ai-web-dev-sdk';

// Initialize ZAI instance (singleton)
let zaiInstance: Awaited<ReturnType<typeof ZAI.create>> | null = null;

async function getZai() {
  if (!zaiInstance) {
    console.log('Initializing ZAI instance...');
    zaiInstance = await ZAI.create();
    console.log('ZAI instance initialized');
  }
  return zaiInstance;
}

// Model mapping for compatibility
const MODEL_MAP: Record<string, string> = {
  'gpt-4': 'glm-4-plus',
  'gpt-4-turbo': 'glm-4-plus',
  'gpt-3.5-turbo': 'glm-4-flash',
  'gpt-3.5': 'glm-4-flash',
  'glm-4': 'glm-4',
  'glm-4-plus': 'glm-4-plus',
  'glm-4-flash': 'glm-4-flash',
  'glm-4-air': 'glm-4-air',
};

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { 
      messages, 
      model = 'glm-4-flash', 
      temperature = 0.7, 
      max_tokens = 2000,
      stream = false 
    } = body;

    if (!messages || !Array.isArray(messages) || messages.length === 0) {
      return NextResponse.json(
        { error: 'Messages array is required and must not be empty' },
        { status: 400 }
      );
    }

    const zai = await getZai();

    // Map model name
    const actualModel = MODEL_MAP[model] || model;

    console.log(`Chat request: model=${actualModel}, messages=${messages.length}`);

    // Call GLM via z-ai-web-dev-sdk
    const completion = await zai.chat.completions.create({
      messages: messages.map((msg: { role: string; content: string | any[] }) => ({
        role: msg.role as 'system' | 'user' | 'assistant',
        content: msg.content,
      })),
      model: actualModel,
      temperature: temperature,
      max_tokens: max_tokens,
    });

    const responseContent = completion.choices[0]?.message?.content || '';

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
            content: responseContent,
          },
          finish_reason: 'stop',
        },
      ],
      usage: {
        prompt_tokens: completion.usage?.prompt_tokens || 0,
        completion_tokens: completion.usage?.completion_tokens || 0,
        total_tokens: completion.usage?.total_tokens || 0,
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
  // Health check - also initialize ZAI
  try {
    await getZai();
    const zaiStatus = 'connected';
  } catch (e) {
    console.error('ZAI init error:', e);
  }

  return NextResponse.json({
    status: 'ok',
    service: 'Ninja AI Proxy - Text Generation',
    models: Object.keys(MODEL_MAP),
    endpoints: {
      'POST /api/ai': 'Chat completions (OpenAI-compatible)',
      'POST /api/ai/vision': 'Vision API for image analysis',
      'POST /api/image': 'Image generation API',
    },
  });
}
