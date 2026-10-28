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
  allowed_email_domains: ['ibotix.ai'],
  departments: [],
  attachment_limits: {
    max_bytes: 5_242_880,
    max_files: 5,
    allowed_mime_types: ['application/pdf', 'image/png', 'image/jpeg', 'text/plain'],
  },
  password_min_length: 12,
  first_response_hours: 24,
};

const configHandler: HttpResponseResolver = ({ request }) =>
  respond(request, () =>
    ok(
      {
        ...PUBLIC_CONFIG,
        departments: db.departments.map((department) => ({
          id: department.id,
          name: department.name,
        })),
        first_response_hours: db.policy.initial_response_hours,
      },
      request,
    ),
  );

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
