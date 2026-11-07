import { Module } from '@nestjs/common';
import { RealtimeGateway } from './realtime.gateway';

/** The browsers' /socket: one connection each, relaying what every package emits (shared RealtimeModule). */
@Module({
    providers: [RealtimeGateway],
})
export class RealtimeGatewayModule {}
