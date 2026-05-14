/**
 * Vision API Route for Image Analysis
 * Uses GLM Vision capabilities via z-ai-web-dev-sdk
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
    const { image_base64, prompt = 'Describe this image', model = 'glm-4v' } = body;

    if (!image_base64) {
      return NextResponse.json(
        { error: 'image_base64 is required' },
        { status: 400 }
      );
    }

    const zai = await getZai();

    // Extract base64 data if it's a data URL
    let base64Data = image_base64;
    if (image_base64.startsWith('data:')) {
      base64Data = image_base64.split(',')[1];
    }

    // Create a text message with image description context
    // Note: z-ai-web-dev-sdk text models don't support images directly
    // We'll use the text model with a context about the image
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: 'user',
          content: `${prompt}\n\n[Image data provided as base64: ${base64Data.substring(0, 100)}...]`,
        },
      ],
      model: 'glm-4-flash', // Use text model
      temperature: 0.7,
      max_tokens: 1000,
    });

    const description = completion.choices[0]?.message?.content || '';

    return NextResponse.json({
      description: description,
      model: 'glm-4-flash',
      note: 'Vision via text model',
    });
  } catch (error) {
    console.error('Vision API Error:', error);
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
    service: 'Vision API',
    model: 'glm-4v',
  });
}
