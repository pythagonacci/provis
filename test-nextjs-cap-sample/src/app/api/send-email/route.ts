import { NextRequest, NextResponse } from 'next/server';
import { renderTemplate } from '../../../lib/email/template';
import { enqueueEmail } from '../../../workers/email/worker';

export async function POST(req: NextRequest) {
  const body = await req.json();
  const html = renderTemplate('welcome', { name: body.name });
  enqueueEmail({ to: body.email, subject: 'Hello', html });
  return NextResponse.json({ ok: true });
}
