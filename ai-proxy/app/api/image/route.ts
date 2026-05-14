/**
 * Image Generation API Route
 * Generates images using z-ai-web-dev-sdk
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

// Valid image sizes for z-ai-web-dev-sdk
const VALID_SIZES = ['1024x1024', '768x1344', '864x1152', '1344x768', '1152x864', '1440x720', '720x1440'] as const;
type ImageSize = typeof VALID_SIZES[number];

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { prompt, size = '1024x1024', n = 1, style, quality } = body;

    if (!prompt) {
      return NextResponse.json(
        { error: 'prompt is required' },
        { status: 400 }
      );
    }

    // Validate size
    const imageSize: ImageSize = VALID_SIZES.includes(size as ImageSize) 
      ? (size as ImageSize) 
      : '1024x1024';

    const zai = await getZai();

    console.log(`Generating image with prompt: "${prompt.substring(0, 100)}..." size: ${imageSize}`);

    // Generate image using z-ai-web-dev-sdk
    const response = await zai.images.generations.create({
      prompt: prompt,
      size: imageSize,
    });

    // Return OpenAI-compatible response with base64 image
    const images = response.data.map((img: { base64?: string; url?: string }) => ({
      b64_json: img.base64 || null,
      url: img.url || null,
    }));

    return NextResponse.json({
      created: Math.floor(Date.now() / 1000),
      data: images,
      model: 'image-gen',
      prompt: prompt,
      size: imageSize,
    });
  } catch (error) {
    console.error('Image Generation API Error:', error);
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
    service: 'Image Generation API',
    sizes: VALID_SIZES,
    usage: {
      method: 'POST',
      body: {
        prompt: 'string (required) - Description of the image to generate',
        size: `string (optional) - Image size, one of: ${VALID_SIZES.join(', ')}`,
        n: 'number (optional) - Number of images (default: 1)',
      },
    },
    example: {
      request: {
        prompt: 'A cute cat playing in a garden with flowers',
        size: '1024x1024'
      }
    }
  });
}
