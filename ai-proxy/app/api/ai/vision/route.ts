/**
 * Vision API Route for Image Analysis
 * Uses VLM (Vision Language Model) via z-ai-web-dev-sdk
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
    const { 
      image_base64, 
      image_url, 
      prompt = 'Describe this image in detail', 
      model = 'glm-4v-flash' 
    } = body;

    if (!image_base64 && !image_url) {
      return NextResponse.json(
        { error: 'image_base64 or image_url is required' },
        { status: 400 }
      );
    }

    const zai = await getZai();

    // Prepare image URL for VLM
    let imageUrl: string;
    if (image_base64) {
      // Convert base64 to data URL
      imageUrl = image_base64.startsWith('data:')
        ? image_base64
        : `data:image/jpeg;base64,${image_base64}`;
    } else {
      imageUrl = image_url!;
    }

    // Use VLM (Vision Language Model) for image understanding
    // The VLM skill handles multimodal input
    const completion = await zai.chat.completions.create({
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: imageUrl } },
          ] as any,
        },
      ],
      model: model,
      temperature: 0.7,
      max_tokens: 2000,
    });

    const description = completion.choices[0]?.message?.content || '';

    return NextResponse.json({
      id: `vision-${Date.now()}`,
      description: description,
      model: model,
      prompt: prompt,
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
    service: 'Vision API - Image Analysis',
    models: ['glm-4v-flash', 'glm-4v'],
    usage: {
      method: 'POST',
      body: {
        image_base64: 'string (optional) - Base64 encoded image',
        image_url: 'string (optional) - URL of the image',
        prompt: 'string (optional) - Question about the image',
        model: 'string (optional) - Vision model, default: glm-4v-flash',
      },
    },
    example: {
      request: {
        image_base64: '/9j/4AAQSkZJRg...',
        prompt: 'What objects are in this image?'
      }
    }
  });
}
