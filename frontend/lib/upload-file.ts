export const DOCUMENT_MIME_TYPES = ['application/pdf', 'image/png', 'image/jpeg'];
export const MAX_DOCUMENT_BYTES = 20 * 1024 * 1024;

export function validateDocumentFile(file: Pick<File, 'type' | 'size'>) {
  if (file.size > MAX_DOCUMENT_BYTES) throw new Error('Files must be smaller than 20 MB.');
  if (!DOCUMENT_MIME_TYPES.includes(file.type)) throw new Error('Unsupported file type. Choose a PDF, PNG, or JPG document. TXT, CSV and Office documents are not supported by the document uploader.');
}
