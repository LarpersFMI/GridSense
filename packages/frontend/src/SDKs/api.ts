import axios from 'axios'

const REQUEST_TIMEOUT_MS = 25_000

/** The server, through Vite's proxy in dev (`/api`). Every SDK calls it through the shared `*.API` functions. */
export const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '',
    timeout: REQUEST_TIMEOUT_MS,
})

export function errorMessage(error: unknown): string {
    if (axios.isAxiosError(error)) {
        const message: unknown = error.response?.data?.message

        if (Array.isArray(message))
            return message.join('\n')

        if (typeof message === 'string')
            return message

        if (!error.response)
            return "Can't reach GridSense. Check that the server is running and try again."
    }

    if (error instanceof Error)
        return error.message

    return String(error)
}

/** What to log about a failure: never the whole error, which carries the request. */
export function describeError(error: unknown): Record<string, unknown> {
    if (axios.isAxiosError(error))
        return {
            message: errorMessage(error),
            status:  error.response?.status,
            method:  error.config?.method?.toUpperCase(),
            url:     error.config?.url,
        }

    if (error instanceof Error)
        return { message: error.message, stack: error.stack }

    return { message: String(error) }
}
