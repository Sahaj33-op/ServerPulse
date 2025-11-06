// MongoDB initialization script for ServerPulse
// This script sets up the database with proper collections and indexes

print('=== ServerPulse MongoDB Initialization ===');

// Switch to serverPulse database
db = db.getSiblingDB('serverpulse');

// Create collections with validation schemas
print('Creating collections with validation schemas...');

// Guild settings collection
db.createCollection('guild_settings', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['guild_id', 'setup_completed', 'created_at'],
            properties: {
                guild_id: {
                    bsonType: 'long',
                    description: 'Discord guild ID'
                },
                guild_name: {
                    bsonType: 'string',
                    description: 'Guild name'
                },
                setup_completed: {
                    bsonType: 'bool',
                    description: 'Whether initial setup is complete'
                },
                update_channel_id: {
                    bsonType: ['long', 'null'],
                    description: 'Channel ID for updates'
                },
                tracked_channels: {
                    bsonType: 'array',
                    items: {
                        bsonType: 'long'
                    },
                    description: 'Array of tracked channel IDs'
                },
                alerts_enabled: {
                    bsonType: 'object',
                    description: 'Alert type enablement settings'
                },
                alert_thresholds: {
                    bsonType: 'object',
                    description: 'Custom alert thresholds'
                },
                ai_provider: {
                    bsonType: 'string',
                    description: 'Selected AI provider'
                },
                ai_api_keys: {
                    bsonType: 'object',
                    description: 'Encrypted AI API keys'
                },
                digest_frequency: {
                    bsonType: 'string',
                    enum: ['daily', 'weekly', 'disabled'],
                    description: 'AI digest frequency'
                },
                created_at: {
                    bsonType: 'date',
                    description: 'Guild settings creation date'
                },
                updated_at: {
                    bsonType: 'date',
                    description: 'Last update timestamp'
                }
            }
        }
    }
});

// Messages collection (aggregated data only)
db.createCollection('messages', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['guild_id', 'channel_id', 'user_id', 'timestamp', 'message_length'],
            properties: {
                guild_id: {
                    bsonType: 'long',
                    description: 'Discord guild ID'
                },
                channel_id: {
                    bsonType: 'long',
                    description: 'Discord channel ID'
                },
                user_id: {
                    bsonType: 'long',
                    description: 'Discord user ID'
                },
                timestamp: {
                    bsonType: 'date',
                    description: 'Message timestamp'
                },
                message_length: {
                    bsonType: 'int',
                    minimum: 0,
                    description: 'Message character length'
                },
                has_attachment: {
                    bsonType: 'bool',
                    description: 'Whether message has attachments'
                }
            }
        }
    }
});

// Member events collection
db.createCollection('member_events', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['guild_id', 'user_id', 'event_type', 'timestamp'],
            properties: {
                guild_id: {
                    bsonType: 'long',
                    description: 'Discord guild ID'
                },
                user_id: {
                    bsonType: 'long',
                    description: 'Discord user ID'
                },
                event_type: {
                    bsonType: 'string',
                    enum: ['join', 'leave'],
                    description: 'Member event type'
                },
                timestamp: {
                    bsonType: 'date',
                    description: 'Event timestamp'
                }
            }
        }
    }
});

// Voice events collection
db.createCollection('voice_events', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['guild_id', 'user_id', 'event_type', 'timestamp'],
            properties: {
                guild_id: {
                    bsonType: 'long',
                    description: 'Discord guild ID'
                },
                user_id: {
                    bsonType: 'long',
                    description: 'Discord user ID'
                },
                channel_id: {
                    bsonType: ['long', 'null'],
                    description: 'Voice channel ID (null for disconnects)'
                },
                event_type: {
                    bsonType: 'string',
                    enum: ['join', 'leave', 'move'],
                    description: 'Voice event type'
                },
                timestamp: {
                    bsonType: 'date',
                    description: 'Event timestamp'
                }
            }
        }
    }
});

// AI reports collection
db.createCollection('ai_reports', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['guild_id', 'report_type', 'content', 'timestamp'],
            properties: {
                guild_id: {
                    bsonType: 'long',
                    description: 'Discord guild ID'
                },
                report_type: {
                    bsonType: 'string',
                    enum: ['instant', 'daily_digest', 'weekly_digest'],
                    description: 'Type of AI report'
                },
                content: {
                    bsonType: 'string',
                    description: 'AI-generated report content'
                },
                metadata: {
                    bsonType: 'object',
                    description: 'Additional report metadata'
                },
                timestamp: {
                    bsonType: 'date',
                    description: 'Report generation timestamp'
                }
            }
        }
    }
});

print('Collections created successfully!');

// Create indexes for optimal performance
print('Creating database indexes...');

// Guild settings indexes
db.guild_settings.createIndex({ 'guild_id': 1 }, { unique: true });
db.guild_settings.createIndex({ 'setup_completed': 1 });

// Messages collection indexes
db.messages.createIndex({ 'guild_id': 1, 'timestamp': -1 });
db.messages.createIndex({ 'guild_id': 1, 'channel_id': 1, 'timestamp': -1 });
db.messages.createIndex({ 'guild_id': 1, 'user_id': 1, 'timestamp': -1 });
db.messages.createIndex({ 'timestamp': 1 }); // For cleanup operations

// Member events indexes
db.member_events.createIndex({ 'guild_id': 1, 'timestamp': -1 });
db.member_events.createIndex({ 'guild_id': 1, 'event_type': 1, 'timestamp': -1 });
db.member_events.createIndex({ 'timestamp': 1 }); // For cleanup

// Voice events indexes
db.voice_events.createIndex({ 'guild_id': 1, 'timestamp': -1 });
db.voice_events.createIndex({ 'guild_id': 1, 'channel_id': 1, 'timestamp': -1 });
db.voice_events.createIndex({ 'timestamp': 1 }); // For cleanup

// AI reports indexes
db.ai_reports.createIndex({ 'guild_id': 1, 'timestamp': -1 });
db.ai_reports.createIndex({ 'guild_id': 1, 'report_type': 1, 'timestamp': -1 });
db.ai_reports.createIndex({ 'timestamp': 1 }); // For cleanup

print('Indexes created successfully!');

// Create initial admin user (optional)
print('Setting up database user...');

// Note: In production, you should create a dedicated user with limited permissions
// This is handled by Docker Compose environment variables

print('=== ServerPulse MongoDB Setup Complete ===');
print('Database: serverpulse');
print('Collections: guild_settings, messages, member_events, voice_events, ai_reports');
print('Indexes: Optimized for analytics queries');
print('Validation: Schema validation enabled for data integrity');
