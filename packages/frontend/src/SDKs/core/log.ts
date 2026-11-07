// The browser's System.log: the same Log interface as the server's
// (`withContext(context).error(message, meta)`, @gridsense/shared/server/system), written to the console.

export type LogLevel = 'debug' | 'info' | 'warning' | 'error'

type Meta = Record<string, unknown>

export interface Log {
    debug:       (message: string, meta?: Meta) => void
    info:        (message: string, meta?: Meta) => void
    warning:     (message: string, meta?: Meta) => void
    error:       (message: string, meta?: Meta) => void
    withContext: (context: string) => Log
}

const SINKS: Record<LogLevel, (...data: unknown[]) => void> = {
    debug:   console.debug,
    info:    console.info,
    warning: console.warn,
    error:   console.error,
}

function write(level: LogLevel, message: string, meta: Meta | undefined, context: string | undefined): void {
    const prefix = context ? `[${context}] ` : ''

    if (meta === undefined)
        SINKS[level](`${prefix}${message}`)
    else
        SINKS[level](`${prefix}${message}`, meta)
}

function createLog(context?: string): Log {
    return {
        debug:       (message, meta) => write('debug', message, meta, context),
        info:        (message, meta) => write('info', message, meta, context),
        warning:     (message, meta) => write('warning', message, meta, context),
        error:       (message, meta) => write('error', message, meta, context),
        withContext: next => createLog(next),
    }
}

export const log = createLog()
