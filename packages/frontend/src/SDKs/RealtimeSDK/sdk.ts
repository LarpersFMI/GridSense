import { createWithEqualityFn } from 'zustand/traditional'
import { immer } from 'zustand/middleware/immer'
import { shallow } from 'zustand/shallow'
import type { z } from 'zod'
import { Realtime } from '@gridsense/shared/domain'
import { BaseSDK } from '../core/BaseSDK'
import { log } from '../core/log'
import { SDK } from '../SDKManager'

// Reconnecting backs off exponentially from 1 s to 30 s, plus up to 1 s of jitter.
const BASE_RECONNECT_DELAY_MS = 1_000
const MAX_RECONNECT_DELAY_MS = 30_000
const RECONNECT_JITTER_MS = 1_000

type Listener = (event: Realtime.Event) => void

/**
 * The browser's live connection (Quarry's RealtimeSDK, without auth): one WebSocket to the server's /socket.
 * SDKs subscribe to channels and get each event on them, parsed with the channel's schema. Reconnects with
 * backoff, subscribing again to every channel still in use.
 */
@SDK('Realtime')
export class RealtimeSDKImpl extends BaseSDK<RealtimeSDK.State> {

    public readonly useStore: BaseSDK.Store<RealtimeSDK.State> = createWithEqualityFn(
        immer<RealtimeSDK.State>(() => ({
            isConnected: false,
        })),
        shallow,
    )

    private readonly log = log.withContext('Realtime')

    private socket: WebSocket | null = null

    private readonly listeners = new Map<Realtime.Channel, Set<Listener>>()

    private reconnectTimeout: ReturnType<typeof setTimeout> | null = null

    private reconnectAttempts = 0

    /** Opens the socket; call once at startup (main.tsx). */
    public connect(): void {
        this.clearReconnect()
        this.closeSocket()

        const socket = new WebSocket(socketUrl())

        socket.onopen = () => {
            this.reconnectAttempts = 0

            this.setState(state => {
                state.isConnected = true
            })

            for (const channel of this.listeners.keys())
                this.send({ action: 'subscribe', channel })
        }

        socket.onclose = () => {
            this.setState(state => {
                state.isConnected = false
            })

            this.scheduleReconnect()
        }

        socket.onmessage = message => {
            this.dispatch(message.data)
        }

        this.socket = socket
    }

    /**
     * Listens to a channel until the returned function is called; the last listener leaving unsubscribes on the
     * server. Each event is parsed with `schema` first (JSON has no dates); one that doesn't fit is dropped.
     */
    public subscribeToChannel<E extends Realtime.Event>(
        channel: Realtime.Channel,
        schema: z.ZodType<E>,
        listener: (event: E) => void,
    ): () => void {
        if (!this.listeners.has(channel)) {
            this.listeners.set(channel, new Set())
            this.send({ action: 'subscribe', channel })
        }

        const channelListener: Listener = event => {
            const parsed = schema.safeParse(event)

            if (!parsed.success) {
                this.log.warning(`Ignored an unexpected event on ${channel}`, { issues: parsed.error.issues })

                return
            }

            listener(parsed.data)
        }

        this.listeners.get(channel)?.add(channelListener)

        return () => {
            const channelListeners = this.listeners.get(channel)

            if (!channelListeners)
                return

            channelListeners.delete(channelListener)

            if (channelListeners.size === 0) {
                this.listeners.delete(channel)
                this.send({ action: 'unsubscribe', channel })
            }
        }
    }

    public override cleanup(): void {
        this.clearReconnect()
        this.closeSocket()
        this.listeners.clear()
        this.reconnectAttempts = 0
    }

    private dispatch(raw: unknown): void {
        let event: Realtime.Event

        try {
            event = Realtime.Event.Base.loose().parse(JSON.parse(String(raw)))
        }
        catch {
            this.log.warning('Ignored a malformed message')

            return
        }

        for (const listener of this.listeners.get(event.channel) ?? [])
            listener(event)
    }

    private send(message: Realtime.ClientMessage): void {
        // Not open yet: onopen subscribes to every channel in use.
        if (this.socket?.readyState === WebSocket.OPEN)
            this.socket.send(JSON.stringify(message))
    }

    private scheduleReconnect(): void {
        if (this.reconnectTimeout)
            return

        const delay = Math.min(BASE_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempts, MAX_RECONNECT_DELAY_MS)
        const jitter = Math.random() * RECONNECT_JITTER_MS

        this.reconnectTimeout = setTimeout(() => {
            this.reconnectTimeout = null
            this.reconnectAttempts++

            this.connect()
        }, delay + jitter)
    }

    private clearReconnect(): void {
        if (this.reconnectTimeout)
            clearTimeout(this.reconnectTimeout)

        this.reconnectTimeout = null
    }

    private closeSocket(): void {
        if (!this.socket)
            return

        this.socket.onclose = null
        this.socket.close()
        this.socket = null

        this.setState(state => {
            state.isConnected = false
        })
    }
}

/** The server's /socket: same origin in dev (Vite proxies it) unless VITE_API_URL names the server. */
function socketUrl(): string {
    const server = new URL(import.meta.env.VITE_API_URL || window.location.origin)
    let protocol = 'ws:'

    if (server.protocol === 'https:')
        protocol = 'wss:'

    return `${protocol}//${server.host}/socket`
}

export const RealtimeSDK = SDK.get<RealtimeSDKImpl>('Realtime')

export namespace RealtimeSDK {

    export type State = {
        isConnected: boolean
    }
}
