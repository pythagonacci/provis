export type EmailJob = { to: string; subject: string; html: string };
export function enqueueEmail(job: EmailJob) {
  // mock queue
  console.log('enqueue', job);
}
