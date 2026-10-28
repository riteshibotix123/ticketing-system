/**
 * Handler registry. Importing this module seeds the in-memory database
 * (idempotent) and composes every endpoint group. An OPTIONS catch-all comes
 * first so browser preflights are answered before any route matching — MSW
 * does not handle CORS itself (spec: dev API runs on another port).
 */
import { http, HttpResponse } from 'msw';
import { seedDatabase } from '../seed';
import { publicHandlers } from './public';
import { authHandlers } from './auth';
import { userHandlers } from './users';
import { signupRequestHandlers } from './signupRequests';
import { adminHandlers } from './admins';
import { departmentHandlers } from './departments';
import { departmentExtrasHandlers } from './departmentExtras';
import { ticketHandlers } from './tickets';
import { ticketDetailHandlers } from './ticketDetail';
import { ticketActionHandlers } from './ticketActions';
import { ticketUpdateHandlers } from './ticketUpdates';
import { ticketCloseHandlers } from './ticketClose';
import { notificationHandlers, auditHandlers, dashboardHandlers } from './ops';
import { p } from './paths';

seedDatabase();

/** CORS preflight for the cross-origin dev API (credentials mode). */
const optionsHandler = http.options(p('/*'), ({ request }) => {
  const origin = request.headers.get('origin') ?? '*';
  return new HttpResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET,POST,PATCH,PUT,DELETE,OPTIONS',
      'Access-Control-Allow-Headers':
        request.headers.get('access-control-request-headers') ?? 'Authorization, Content-Type',
      'Access-Control-Max-Age': '86400',
      Vary: 'Origin',
    },
  });
});

export const handlers = [
  optionsHandler,
  ...publicHandlers,
  ...authHandlers,
  ...userHandlers,
  ...signupRequestHandlers,
  ...adminHandlers,
  ...departmentHandlers,
  ...departmentExtrasHandlers,
  ...ticketHandlers,
  ...ticketDetailHandlers,
  ...ticketActionHandlers,
  ...ticketUpdateHandlers,
  ...ticketCloseHandlers,
  ...notificationHandlers,
  ...auditHandlers,
  ...dashboardHandlers,
];
