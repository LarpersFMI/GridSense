import { Global, Injectable, Module } from "@nestjs/common"
import type { Realtime } from "../domain"
import { sharedRedis } from "./redis"

/**
 * Publishes live events over Redis pub/sub, on the channel each event names. The server's RealtimeGateway
 * relays them to the browsers subscribed to that channel. Any package may emit.
 */
@Injectable()
export class RealtimeService {

    public emitEvent<T extends Realtime.Event>(event: T): void {
        void sharedRedis().publish(event.channel, JSON.stringify(event))
    }
}

@Global()
@Module({
    providers: [RealtimeService],
    exports:   [RealtimeService],
})
export class RealtimeModule {}
