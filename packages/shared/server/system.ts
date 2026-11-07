export type LogLevel = "debug" | "info" | "warning" | "error"

type Meta = Record<string, unknown>

const LEVEL_ORDER: Record<LogLevel, number> = {
    debug:   10,
    info:    20,
    warning: 30,
    error:   40,
}

const COLOR: Record<LogLevel, string> = {
    debug:   "\x1b[35m",
    info:    "\x1b[32m",
    warning: "\x1b[33m",
    error:   "\x1b[31m",
}

const CONTEXT_COLOR = "\x1b[33m"
const DIM = "\x1b[2m"
const RESET = "\x1b[0m"

export interface Log {
    debug:   (message: string, meta?: Meta) => void
    info:    (message: string, meta?: Meta) => void
    warning: (message: string, meta?: Meta) => void
    error:   (message: string, meta?: Meta) => void
}

/** One line per message: time, app, level, context, message, meta. LOG_LEVEL sets the threshold (default info). */
class LogService {

    private appName = "App"

    public setAppName(name: string): void {
        this.appName = name
    }

    public withContext(context: string): Log {
        return {
            debug:   (message, meta) => this.write("debug", context, message, meta),
            info:    (message, meta) => this.write("info", context, message, meta),
            warning: (message, meta) => this.write("warning", context, message, meta),
            error:   (message, meta) => this.write("error", context, message, meta),
        }
    }

    private write(level: LogLevel, context: string, message: string, meta?: Meta): void {
        const threshold = LEVEL_ORDER[(process.env.LOG_LEVEL ?? "info") as LogLevel] ?? LEVEL_ORDER.info

        if (LEVEL_ORDER[level] < threshold)
            return

        const time = new Date().toISOString().slice(11, 23)
        let line = `${DIM}${time}${RESET} ${this.appName} ${COLOR[level]}${level.toUpperCase().padEnd(7)}${RESET} ${CONTEXT_COLOR}[${context}]${RESET} ${message}`

        if (meta !== undefined)
            line += ` ${DIM}${JSON.stringify(meta, (_, value) => value instanceof Error ? value.message : value)}${RESET}`

        if (level === "error")
            console.error(line)
        else
            console.log(line)
    }
}

/** Process-wide services every package uses: the logger. */
export namespace System {

    export const log = new LogService()
}
