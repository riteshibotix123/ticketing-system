/**
 * Public endpoints: runtime config (spec 6 / requirement 10) and the dev-only
 * persona list consumed by the DevPanel.
 */
import { http, type HttpResponseResolver } from 'msw';
import type { PublicConfig } from '@/types/domain';
import { db } from '../db';
import { ok, respond } from '../helpers';
import { personas } from '../auth';
import { p } from './paths';

export const PUBLIC_CONFIG: PublicConfig = {
  app_name: 'Ibotix Tickets',
  allowed_email_domains: ['ibotix.ai'],
  max_attachment_bytes: 5_242_880, // 5 MB
  allowed_attachment_mimes: ['application/pdf', 'image/png', 'image/jpeg', 'text/plain'],
  personas_enabled: true,
  demo_clock_enabled: true,
};

const configHandler: HttpResponseResolver = ({ request }) =>
  respond(request, () => ok(PUBLIC_CONFIG, request));

const devPersonasHandler: HttpResponseResolver = ({ request }) =>
  respond(request, () =>
    ok(
      {
        items: personas(),
        clock_offset_ms: db.clockOffsetMs,
        demo_password_hint: 'IbotixDemo@2026',
      },
      request,
    ),
  );

export const publicHandlers = [
  http.get(p('/public/config'), configHandler),
  http.get(p('/dev/personas'), devPersonasHandler),
];
