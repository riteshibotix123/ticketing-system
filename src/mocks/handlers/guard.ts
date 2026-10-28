/**
 * Shared request guard: resolve the bearer token to the acting user or throw
 * the standard 401 envelope. Used by every authenticated handler group.
 */
import { resolveToken } from '../auth';
import { type DbUser } from '../db';
import { bearer, throw401 } from '../helpers';

export function requireUser(request: Request): DbUser {
  const user = resolveToken(bearer(request));
  if (!user) throw401();
  return user;
}
