/**
 * Ticket reads and comments (spec 6.3, 9.6, 9.8, 9.9): detail, the
 * caller-filtered timeline, public comments and internal notes (never visible
 * to requesters), plus multipart attachment upload with config-driven limits.
 */
import { http } from 'msw';
import type { Comment, Ticket, TimelineEvent } from '@/types/domain';
import { db, findTicket, HOUR_MS, uid, type DbTicket } from '../db';
import {
  actorRef,
  notifyUsers,
  nowIso,
  ok,
  pushEvent,
  readJson,
  respond,
  str,
  throw403,
  throw404,
  throw422,
} from '../helpers';
import { canSeeTicket, loadVisibleTicket, timelineFor, ticketDto } from '../access';
import { recomputeSla } from '../sla';
import { PUBLIC_CONFIG } from './public';
import { requireUser } from './guard';
import { p } from './paths';

/** Resolve uploaded attachment ids, dropping unknown ones. */
export function resolveAttachments(ids: unknown): Ticket['attachments'] {
  if (!Array.isArray(ids)) return [];
  return ids
    .map((id) => db.attachments[String(id)])
    .filter((a): a is NonNullable<typeof a> => Boolean(a));
}

/** Load a visible ticket or throw the generic 404 (confidential-safe). */
function loadCommentable(id: string, user: ReturnType<typeof requireUser>): DbTicket {
  const rec = findTicket(id);
  if (!rec || !canSeeTicket(user, rec.ticket)) throw404();
  return rec;
}

export const ticketDetailHandlers = [
  http.get(p('/tickets/:id'), ({ params, request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const rec = loadVisibleTicket(String(params.id), user);
      return ok(ticketDto(rec, user), request);
    }),
  ),

  http.get(p('/tickets/:id/timeline'), ({ params, request }) =>
    respond(request, () => {
      const user = requireUser(request);
      const rec = loadVisibleTicket(String(params.id), user);
      const events: TimelineEvent[] = timelineFor(rec, user);
      return ok(events, request);
    }),
  ),

  http.post(p('/tickets/:id/comments'), ({ params, request }) =>
    respond(request, async () => {
      const user = requireUser(request);
      const rec = loadCommentable(String(params.id), user);
      const body = await readJson<{ body?: string; internal?: boolean }>(request);
      const text = str(body.body);
      if (!text) throw422({ body: 'Write something first.' });
      const internal = body.internal === true;
      // Spec 4.2/10.11: only staff post internal notes; requesters never can.
      if (internal && !user.roles.some((r) => r !== 'employee')) throw403();

      const comment: Comment = {
        id: uid('cmt'),
        ticket_id: rec.ticket.id,
        author: actorRef(user),
        created_at: nowIso(),
        body: text,
        internal,
      };
      pushEvent(rec, {
        actor: actorRef(user),
        type: internal ? 'internal_note' : 'comment',
        body: text,
        public: !internal,
      });
      if (!internal) {
        // A public team comment counts as a progress update.
        const now = Date.now();
        rec.ticket.last_team_update_at = new Date(now).toISOString();
        rec.update_due = now + db.policy.update_cadence_hours * HOUR_MS;
        rec.update_shift = 0;
        rec.pause = null;
      }
      recomputeSla(rec);

      if (internal) {
        const staffIds = [rec.ticket.owner?.id, rec.ticket.assignee?.id].filter((x): x is string =>
          Boolean(x),
        );
        notifyUsers(staffIds, {
          text: `Internal note added on ${rec.ticket.id} by ${user.name}.`,
          kind: 'internal_note',
          ticket_id: rec.ticket.id,
        });
      }
      return ok(comment, request, 201);
    }),
  ),

  http.post(p('/attachments'), ({ request }) =>
    respond(request, async () => {
      requireUser(request);
      let file: File | null = null;
      try {
        const form = await request.formData();
        const entry = form.get('file');
        if (entry instanceof File) file = entry;
      } catch {
        /* not multipart */
      }
      if (!file) throw422({ file: 'Choose a file to upload.' });
      const max = PUBLIC_CONFIG.max_attachment_bytes;
      if (file.size > max) {
        throw422({ file: `Attachments must be ${Math.round(max / 1_048_576)} MB or smaller.` });
      }
      if (!PUBLIC_CONFIG.allowed_attachment_mimes.includes(file.type)) {
        throw422({ file: `Allowed types: ${PUBLIC_CONFIG.allowed_attachment_mimes.join(', ')}.` });
      }
      const id = uid('att');
      const attachment = {
        id,
        name: file.name,
        size: file.size,
        mime: file.type,
        scan_status: 'clean' as const,
        url: `/mock-attachments/${id}`,
      };
      db.attachments[id] = attachment;
      return ok(attachment, request, 201);
    }),
  ),
];
