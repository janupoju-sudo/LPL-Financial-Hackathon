import type { Role } from './types';

export const canUploadDocuments = (role: Role) => role === 'owner' || role === 'ops';
export const canReviewDocuments = (role: Role) => role === 'owner' || role === 'ops';
export const canManageRules = (role: Role) => role === 'owner';
export const canImportTransactions = (role: Role) => role === 'owner' || role === 'ops';

export function canApproveBill(role: Role, requiredApprovers: string[] | undefined, createdBy: string | undefined, userId = '') {
  if (userId && createdBy === userId) return false;
  return role === 'owner' || (role === 'partner' && Boolean(requiredApprovers?.includes(role)));
}
