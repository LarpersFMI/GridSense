import type { OnModuleDestroy } from '@nestjs/common';
import { type OnGatewayConnection, type OnGatewayDisconnect, WebSocketGateway } from '@nestjs/websockets';
import { WebSocket } from 'ws';
import { Realtime } from '@gridsense/shared/domain';
import { redisSubscriber } from '@gridsense/shared/server/redis';
import { System } from '@gridsense/shared/server/system';

const log = System.log.withContext('Realtime');

/**
 * The browser's live connection (Quarry's RealtimeGateway, without authorization): one WebSocket at /socket.
 * A client sends `{ action: 'subscribe' | 'unsubscribe', channel }`; Redis messages on its channels are
 * relayed to it. A channel is subscribed in Redis while at least one socket listens to it.
 */
@WebSocketGateway({ path: '/socket' })
export class RealtimeGateway implements OnGatewayConnection, OnGatewayDisconnect, OnModuleDestroy {

    private readonly redis = redisSubscriber();

    private readonly subscriptions = new Map<Realtime.Channel, Set<WebSocket>>();

    constructor() {
        this.redis.on('message', (channel: string, message: string) => {
            for (const socket of this.subscriptions.get(Realtime.Channel.parse(channel)) ?? []) {
                if (socket.readyState === WebSocket.OPEN)
                    socket.send(message);
            }
        });
    }

    public handleConnection(socket: WebSocket): void {
        socket.on('message', (data) => {
            let message: Realtime.ClientMessage;

            try {
                message = Realtime.ClientMessage.parse(JSON.parse(data.toString()));
            }
            catch {
                log.warning('Ignored a malformed socket message');

                return;
            }

            if (message.action === 'subscribe')
                this.add(socket, message.channel);
            else
                this.remove(socket, message.channel);
        });
    }

    public handleDisconnect(socket: WebSocket): void {
        for (const channel of [...this.subscriptions.keys()])
            this.remove(socket, channel);
    }

    public async onModuleDestroy(): Promise<void> {
        await this.redis.quit();
    }

    private add(socket: WebSocket, channel: Realtime.Channel): void {
        if (!this.subscriptions.has(channel)) {
            this.subscriptions.set(channel, new Set());
            void this.redis.subscribe(channel);
        }

        this.subscriptions.get(channel)!.add(socket);
    }

    private remove(socket: WebSocket, channel: Realtime.Channel): void {
        const sockets = this.subscriptions.get(channel);

        if (!sockets)
            return;

        sockets.delete(socket);

        if (sockets.size === 0) {
            this.subscriptions.delete(channel);
            void this.redis.unsubscribe(channel);
        }
    }
}
