const { Telegraf, Markup } = require('telegraf');
const fs = require('fs');
const path = require('path');

// ============================================
// CONFIGURATION
// ============================================
const BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE';  // Replace with your bot token from @BotFather

// Database file to store videos
const DATABASE_FILE = path.join(__dirname, 'videos.json');

// Video database
let videoDatabase = {
    girls: [],
    boys: []
};

// Load database
function loadDatabase() {
    if (fs.existsSync(DATABASE_FILE)) {
        try {
            const data = fs.readFileSync(DATABASE_FILE, 'utf8');
            videoDatabase = JSON.parse(data);
            console.log('✅ Database loaded');
        } catch (err) {
            console.error('Error loading database:', err);
        }
    } else {
        saveDatabase();
    }
}

function saveDatabase() {
    try {
        fs.writeFileSync(DATABASE_FILE, JSON.stringify(videoDatabase, null, 2));
        console.log('💾 Database saved');
    } catch (err) {
        console.error('Error saving database:', err);
    }
}

// Check if user is Group Admin or Owner
async function isGroupAdmin(ctx, userId) {
    try {
        const chatMember = await ctx.getChatMember(userId);
        return chatMember.status === 'administrator' || chatMember.status === 'creator';
    } catch (err) {
        return false;
    }
}

// ============================================
// BOT INITIALIZATION
// ============================================
const bot = new Telegraf(BOT_TOKEN);
loadDatabase();

// Store welcome message and video to be sent in group
let welcomeSettings = {
    girls: {
        message: "🌸 Welcome to the group, {name}! You have been identified as a Female.\n\nEnjoy your stay! 🎉",
        videoFileId: null
    },
    boys: {
        message: "🔥 Welcome to the group, {name}! You have been identified as a Male.\n\nEnjoy your stay! 🎉",
        videoFileId: null
    }
};

// Store temporary admin session for setting videos
const adminSession = new Map(); // userId -> { gender, step }

// ============================================
// WHEN BOT ADDS TO GROUP
// ============================================
bot.on('my_chat_member', async (ctx) => {
    const newStatus = ctx.myChatMember.new_chat_member.status;
    const chatId = ctx.chat.id;
    const chatType = ctx.chat.type;
    
    if ((newStatus === 'member' || newStatus === 'administrator') && (chatType === 'supergroup' || chatType === 'group')) {
        console.log(`✅ Bot added to group: ${chatId}`);
        
        const keyboard = Markup.inlineKeyboard([
            [Markup.button.callback('👩 Set Welcome for GIRLS', 'admin_set_girls')],
            [Markup.button.callback('👨 Set Welcome for BOYS', 'admin_set_boys')],
            [Markup.button.callback('📹 View Current Settings', 'admin_view_settings')]
        ]);
        
        await ctx.reply(
            `🎉 *Welcome Bot Activated!* 🎉\n\n` +
            `I will welcome new members in this group with video + message.\n\n` +
            `*Setup Instructions:*\n` +
            `1️⃣ Click a button below to set welcome for GIRLS\n` +
            `2️⃣ Send a video (optional) + welcome message\n` +
            `3️⃣ Repeat for BOYS\n\n` +
            `*Note:* Only group admins can change these settings.`,
            { parse_mode: 'Markdown', ...keyboard }
        );
    }
});

// ============================================
// ADMIN SETUP BUTTONS
// ============================================
bot.action('admin_set_girls', async (ctx) => {
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.answerCbQuery('❌ Only group admins can change settings!', { show_alert: true });
        return;
    }
    
    adminSession.set(ctx.from.id, { gender: 'girls', step: 'awaiting_message' });
    
    await ctx.answerCbQuery();
    await ctx.editMessageText(
        `👩 *Setting up WELCOME for GIRLS*\n\n` +
        `Send me the welcome message you want to show when a girl joins.\n\n` +
        `*Available placeholders:*\n` +
        `{name} - Member's first name\n` +
        `{username} - Member's username\n` +
        `{mention} - Mention the member\n\n` +
        `*Example:*\n` +
        `"🌸 Welcome {name}! Happy to have you here!"\n\n` +
        `Send your message now 👇`,
        { parse_mode: 'Markdown' }
    );
});

bot.action('admin_set_boys', async (ctx) => {
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.answerCbQuery('❌ Only group admins can change settings!', { show_alert: true });
        return;
    }
    
    adminSession.set(ctx.from.id, { gender: 'boys', step: 'awaiting_message' });
    
    await ctx.answerCbQuery();
    await ctx.editMessageText(
        `👨 *Setting up WELCOME for BOYS*\n\n` +
        `Send me the welcome message you want to show when a boy joins.\n\n` +
        `*Available placeholders:*\n` +
        `{name} - Member's first name\n` +
        `{username} - Member's username\n` +
        `{mention} - Mention the member\n\n` +
        `*Example:*\n` +
        `"🔥 Welcome {name}! Glad to see you here!"\n\n` +
        `Send your message now 👇`,
        { parse_mode: 'Markdown' }
    );
});

bot.action('admin_view_settings', async (ctx) => {
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.answerCbQuery('❌ Only group admins can view settings!', { show_alert: true });
        return;
    }
    
    let msg = `📹 *CURRENT WELCOME SETTINGS*\n\n`;
    msg += `👩 *GIRLS:*\n`;
    msg += `📝 Message: ${welcomeSettings.girls.message.substring(0, 100)}...\n`;
    msg += `🎬 Video: ${welcomeSettings.girls.videoFileId ? '✅ SET' : '❌ NOT SET'}\n\n`;
    msg += `👨 *BOYS:*\n`;
    msg += `📝 Message: ${welcomeSettings.boys.message.substring(0, 100)}...\n`;
    msg += `🎬 Video: ${welcomeSettings.boys.videoFileId ? '✅ SET' : '❌ NOT SET'}\n\n`;
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.callback('✏️ Edit GIRLS Settings', 'admin_set_girls')],
        [Markup.button.callback('✏️ Edit BOYS Settings', 'admin_set_boys')],
        [Markup.button.callback('🗑️ Clear All Settings', 'admin_clear_all')],
        [Markup.button.callback('❌ Close', 'admin_close')]
    ]);
    
    await ctx.editMessageText(msg, { parse_mode: 'Markdown', ...keyboard });
});

bot.action('admin_clear_all', async (ctx) => {
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.answerCbQuery('❌ Only group admins can do this!', { show_alert: true });
        return;
    }
    
    welcomeSettings = {
        girls: { message: "🌸 Welcome {name}!", videoFileId: null },
        boys: { message: "🔥 Welcome {name}!", videoFileId: null }
    };
    
    await ctx.answerCbQuery('✅ All settings cleared!');
    await ctx.editMessageText(
        `✅ *All welcome settings have been cleared!*\n\n` +
        `Use the buttons below to set new welcome messages and videos.`,
        { parse_mode: 'Markdown', ...Markup.inlineKeyboard([
            [Markup.button.callback('👩 Set GIRLS Welcome', 'admin_set_girls')],
            [Markup.button.callback('👨 Set BOYS Welcome', 'admin_set_boys')]
        ]) }
    );
});

bot.action('admin_close', async (ctx) => {
    await ctx.deleteMessage();
});

// ============================================
// HANDLE ADMIN MESSAGE INPUT
// ============================================
bot.on('text', async (ctx) => {
    const session = adminSession.get(ctx.from.id);
    if (!session) return;
    
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        adminSession.delete(ctx.from.id);
        return;
    }
    
    if (session.step === 'awaiting_message') {
        // Save the message
        const gender = session.gender;
        welcomeSettings[gender].message = ctx.message.text;
        
        adminSession.set(ctx.from.id, { gender: gender, step: 'awaiting_video' });
        
        await ctx.reply(
            `✅ *Message saved for ${gender === 'girls' ? 'GIRLS' : 'BOYS'}!*\n\n` +
            `📝 Your message:\n"${ctx.message.text}"\n\n` +
            `Now send me a WELCOME VIDEO (optional) for ${gender === 'girls' ? 'GIRLS' : 'BOYS'}.\n\n` +
            `• Send a video to set it\n` +
            `• Or type /skip to continue without video`,
            { parse_mode: 'Markdown' }
        );
    }
});

// Handle video upload from admin
bot.on('video', async (ctx) => {
    const session = adminSession.get(ctx.from.id);
    if (!session) return;
    
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        adminSession.delete(ctx.from.id);
        return;
    }
    
    if (session.step === 'awaiting_video') {
        const gender = session.gender;
        welcomeSettings[gender].videoFileId = ctx.message.video.file_id;
        
        adminSession.delete(ctx.from.id);
        
        await ctx.reply(
            `✅ *Welcome setup COMPLETE for ${gender === 'girls' ? 'GIRLS' : 'BOYS'}!*\n\n` +
            `📝 Message: ${welcomeSettings[gender].message}\n` +
            `🎬 Video: ${welcomeSettings[gender].videoFileId ? '✅ SET' : '❌ NOT SET'}\n\n` +
            `Now when a ${gender === 'girls' ? 'girl' : 'boy'} joins the group, they will see this welcome!`,
            { parse_mode: 'Markdown' }
        );
    }
});

// Handle /skip command
bot.command('skip', async (ctx) => {
    const session = adminSession.get(ctx.from.id);
    if (!session) return;
    
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        adminSession.delete(ctx.from.id);
        return;
    }
    
    if (session.step === 'awaiting_video') {
        const gender = session.gender;
        welcomeSettings[gender].videoFileId = null;
        
        adminSession.delete(ctx.from.id);
        
        await ctx.reply(
            `✅ *Welcome setup COMPLETE for ${gender === 'girls' ? 'GIRLS' : 'BOYS'}!*\n\n` +
            `📝 Message: ${welcomeSettings[gender].message}\n` +
            `🎬 Video: NOT SET (skipped)\n\n` +
            `Now when a ${gender === 'girls' ? 'girl' : 'boy'} joins the group, they will see the welcome message.`,
            { parse_mode: 'Markdown' }
        );
    }
});

// ============================================
// NEW MEMBER JOIN HANDLER - WELCOME IN GROUP
// ============================================
bot.on('new_chat_members', async (ctx) => {
    const newMembers = ctx.message.new_chat_members;
    const chatId = ctx.chat.id;
    
    for (const member of newMembers) {
        // Skip if bot itself joined
        if (member.id === bot.botInfo.id) continue;
        
        const userId = member.id;
        const name = member.first_name || 'User';
        const username = member.username || '';
        const mention = username ? `@${username}` : name;
        
        // Show gender selection buttons in GROUP
        const keyboard = Markup.inlineKeyboard([
            [
                Markup.button.callback('👩 I am a GIRL / Female', `welcome_girls_${userId}_${chatId}`),
                Markup.button.callback('👨 I am a BOY / Male', `welcome_boys_${userId}_${chatId}`)
            ]
        ]);
        
        await ctx.reply(
            `🎉 *Welcome to the group, ${name}!* 🎉\n\n` +
            `Please tell us your gender to get a special welcome message:`,
            { parse_mode: 'Markdown', ...keyboard }
        );
        
        // Store for cleanup after 2 minutes
        setTimeout(async () => {
            try {
                await ctx.deleteMessage();
            } catch (err) {}
        }, 120000);
    }
});

// ============================================
// GENDER SELECTION CALLBACK - SEND WELCOME IN GROUP
// ============================================
bot.action(/welcome_(girls|boys)_(\d+)_(\d+)/, async (ctx) => {
    const gender = ctx.match[1];
    const targetUserId = parseInt(ctx.match[2]);
    const groupChatId = parseInt(ctx.match[3]);
    const userId = ctx.from.id;
    
    // Verify that the person clicking is the new member
    if (userId !== targetUserId) {
        await ctx.answerCbQuery('❌ This welcome is not for you!', { show_alert: true });
        return;
    }
    
    await ctx.answerCbQuery(`✅ Welcome ${gender === 'girls' ? 'Girl' : 'Boy'}!`);
    
    // Prepare welcome message with placeholders
    const name = ctx.from.first_name || 'User';
    const username = ctx.from.username || '';
    const mention = username ? `@${username}` : name;
    
    let welcomeMessage = welcomeSettings[gender].message
        .replace(/{name}/g, name)
        .replace(/{username}/g, username)
        .replace(/{mention}/g, mention);
    
    const videoFileId = welcomeSettings[gender].videoFileId;
    
    // Delete the selection message
    try {
        await ctx.deleteMessage();
    } catch (err) {}
    
    // Send welcome in the GROUP
    if (videoFileId) {
        // Send video with caption in group
        await ctx.replyWithVideo(videoFileId, {
            caption: welcomeMessage,
            parse_mode: 'Markdown'
        });
    } else {
        // Send only message in group
        await ctx.reply(welcomeMessage, { parse_mode: 'Markdown' });
    }
    
    // Also send a confirmation message
    await ctx.reply(
        `✅ *${name}*, you have been welcomed as a ${gender === 'girls' ? '🌸 Girl' : '🔥 Boy'}!\n` +
        `Enjoy your time in the group! 🎉`,
        { parse_mode: 'Markdown' }
    );
});

// ============================================
// HELPER COMMANDS
// ============================================
bot.command('settings', async (ctx) => {
    if (ctx.chat.type === 'private') {
        await ctx.reply('❌ Use this command in the GROUP where bot is added!');
        return;
    }
    
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.reply('❌ Only group admins can view settings!', { parse_mode: 'Markdown' });
        return;
    }
    
    let msg = `📹 *WELCOME SETTINGS*\n\n`;
    msg += `👩 *GIRLS:*\n`;
    msg += `📝 Message: ${welcomeSettings.girls.message.substring(0, 80)}...\n`;
    msg += `🎬 Video: ${welcomeSettings.girls.videoFileId ? '✅ SET' : '❌ NOT SET'}\n\n`;
    msg += `👨 *BOYS:*\n`;
    msg += `📝 Message: ${welcomeSettings.boys.message.substring(0, 80)}...\n`;
    msg += `🎬 Video: ${welcomeSettings.boys.videoFileId ? '✅ SET' : '❌ NOT SET'}\n\n`;
    msg += `Use /setup to change settings.`;
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.callback('⚙️ Change Settings', 'admin_set_girls')]
    ]);
    
    await ctx.reply(msg, { parse_mode: 'Markdown', ...keyboard });
});

bot.command('setup', async (ctx) => {
    if (ctx.chat.type === 'private') {
        await ctx.reply('❌ Use this command in the GROUP where bot is added!');
        return;
    }
    
    const isAdmin = await isGroupAdmin(ctx, ctx.from.id);
    if (!isAdmin) {
        await ctx.reply('❌ Only group admins can change settings!', { parse_mode: 'Markdown' });
        return;
    }
    
    const keyboard = Markup.inlineKeyboard([
        [Markup.button.callback('👩 Set Welcome for GIRLS', 'admin_set_girls')],
        [Markup.button.callback('👨 Set Welcome for BOYS', 'admin_set_boys')],
        [Markup.button.callback('📹 View Current Settings', 'admin_view_settings')]
    ]);
    
    await ctx.reply(
        `⚙️ *Welcome Bot Setup*\n\n` +
        `Click a button below to configure welcome messages and videos for new members.\n\n` +
        `Welcome will be sent directly in this GROUP!`,
        { parse_mode: 'Markdown', ...keyboard }
    );
});

bot.command('help', async (ctx) => {
    const isAdmin = ctx.chat.type !== 'private' ? await isGroupAdmin(ctx, ctx.from.id) : false;
    
    let helpMsg = `🤖 *WELCOME BOT HELP*\n\n`;
    helpMsg += `*How it works:*\n`;
    helpMsg += `1️⃣ When someone joins the group\n`;
    helpMsg += `2️⃣ Bot asks for gender\n`;
    helpMsg += `3️⃣ User selects GIRL or BOY\n`;
    helpMsg += `4️⃣ Bot sends welcome video + message in GROUP\n\n`;
    
    helpMsg += `*Admin Commands (Group only):*\n`;
    helpMsg += `/setup - Configure welcome settings\n`;
    helpMsg += `/settings - View current settings\n`;
    helpMsg += `/help - Show this message\n\n`;
    
    helpMsg += `*Setup Steps:*\n`;
    helpMsg += `1️⃣ Type /setup in group\n`;
    helpMsg += `2️⃣ Click "Set Welcome for GIRLS"\n`;
    helpMsg += `3️⃣ Send welcome message (use {name} for member name)\n`;
    helpMsg += `4️⃣ Send a welcome video (optional) or type /skip\n`;
    helpMsg += `5️⃣ Repeat for BOYS\n\n`;
    
    helpMsg += `⚠️ *Make me ADMIN in the group for best results!*`;
    
    await ctx.reply(helpMsg, { parse_mode: 'Markdown' });
});

// ============================================
// ERROR HANDLING
// ============================================
bot.catch((err, ctx) => {
    console.error('Bot error:', err);
    ctx.reply('⚠️ An error occurred. Please try again.');
});

// Launch bot
bot.launch()
    .then(() => {
        console.log('🤖 Welcome Bot is running!');
        console.log('\n📋 Setup Instructions:');
        console.log('1. Add bot to your group');
        console.log('2. Make bot ADMIN in the group');
        console.log('3. Type /setup in group');
        console.log('4. Set welcome message + video for GIRLS');
        console.log('5. Set welcome message + video for BOYS');
        console.log('6. Bot will welcome new members in GROUP!\n');
    });

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
