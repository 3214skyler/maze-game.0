/** Every online failure derives from OnlineError. The game must keep working when these are thrown. */
export class OnlineError extends Error {}
export class NetworkError extends OnlineError {}
export class AuthError extends OnlineError {}
export class ServerError extends OnlineError {
  constructor(readonly code: string, message?: string) {
    super(message || code);
  }
}
