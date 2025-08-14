// Configuration
const DESTINATION = '/public/sigmond-blackjack';  // Same SignalWire destination as tarot
// Using the same token from tarot app
const STATIC_TOKEN = 'eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIiwidHlwIjoiU0FUIiwiY2giOiJwdWMuc2lnbmFsd2lyZS5jb20ifQ..htbs9CftJWJDV5rN.bq37URPcSrpOBSVRczp8QB5Yb84AkDNH4cr1O_U8kIstLT4uJ7BCPaVpE4_qqqviMt7s2owuRRNO9Tx28uXKo7I8i2Df0s5fZm9WrZkgthSwacq8V-9_mPyUMi1Yiha675aZuL2TFot0NrIaiZEt1IEsdEJFtw1SWBie63vUajwMDrY2GU9wN2BozQ6dT_fHUNbNBCbX4lgLaz2lvT0wZ2gf8S0GTCcr799r75h4GY-masEg2-a8CB937Z7UXh1MQhmTbycUQO9v_PSmeRSYL5acz5SMSoMdUd2M4P4QVK3Csyfvd0xJJQkl9tBEenhlI8ipcGsl_YDzvgS6MkLa3FB2NzY8einjHNZ2xYcelifxbC4yzDxHHmjMPmmSuH20zSg7r6VR8IEtVcr0I9Sp6BhKyxoYcivH9IIVhZwF7d618XJE8lWInszxfXBTn_j0zN8Zomgzo7S6-3Ne-_nhvxnIywsoX3Y4tlUx0yrQIljpEsXb2frqryqiv7v94sxqQSHC4UjeG_EgQ5YoUj9yVIgXvZt8J7_5CTL7Pg2jtsytjJecLOLqYdIWupEtkNdE-fhANQMweoamjcXmboeL50AzTYFq.yKhygR6oYAam-9Pe44RSBw';
const BASE_URL = '../card_images';  // Relative path from client directory

let client;
let roomSession;
let isMuted = false;
let gameState = {
    playerHand: [],
    dealerHand: [],
    playerScore: 0,
    dealerScore: 0,
    chips: 1000,
    currentBet: 0,
    gamePhase: 'waiting'
};

// UI Elements
const connectBtn = document.getElementById('connectBtn');
const hangupBtn = document.getElementById('hangupBtn');
const muteBtn = document.getElementById('muteBtn');
const startMutedCheckbox = document.getElementById('startMuted');
const showLogCheckbox = document.getElementById('showLog');
const statusDiv = document.getElementById('status');
const eventLog = document.getElementById('event-log');
const eventLogHeader = document.getElementById('event-log-header');
const eventEntries = document.getElementById('event-entries');

// Game UI Elements
const chipCount = document.getElementById('chipCount');
const betAmount = document.getElementById('betAmount');
const playerCards = document.getElementById('playerCards');
const dealerCards = document.getElementById('dealerCards');
const playerScore = document.getElementById('playerScore');
const dealerScore = document.getElementById('dealerScore');
const gameActions = document.getElementById('gameActions');
const resultMessage = document.getElementById('resultMessage');

// Event logging
function logEvent(message, data = null, isUserEvent = false) {
    const entry = document.createElement('div');
    entry.className = isUserEvent ? 'event-entry user-event' : 'event-entry';
    const time = new Date().toLocaleTimeString();
    
    let dataStr = '';
    if (data) {
        try {
            const seen = new WeakSet();
            dataStr = JSON.stringify(data, (key, value) => {
                if (typeof value === 'object' && value !== null) {
                    if (seen.has(value)) {
                        return '[Circular Reference]';
                    }
                    seen.add(value);
                }
                return value;
            }, 2);
        } catch (e) {
            dataStr = 'Error serializing data: ' + e.message;
        }
    }
    
    entry.innerHTML = `
        <div class="event-time">${time}</div>
        <div>${isUserEvent ? '🎲 GAME EVENT: ' : ''}${message}</div>
        ${dataStr ? `<div style="color: #888; margin-left: 10px;">${dataStr}</div>` : ''}
    `;
    eventEntries.appendChild(entry);
    eventEntries.scrollTop = eventEntries.scrollHeight;
}

// Card display functions
function getCardImagePath(card) {
    if (!card) return `${BASE_URL}/card_back.png`;
    
    // The bot now sends the correct filename directly
    if (card.image) {
        return `${BASE_URL}/${card.image}`;
    }
    
    // Fallback to constructing filename if image not provided
    return `${BASE_URL}/${card.rank}_of_${card.suit}.png`;
}

function displayCard(container, card, faceDown = false) {
    const cardDiv = document.createElement('div');
    cardDiv.className = 'card';
    
    console.log('displayCard called with:', { card, faceDown, container: container.id });
    
    if (faceDown) {
        cardDiv.classList.add('face-down');
        const img = document.createElement('img');
        img.src = `${BASE_URL}/card_back.png`;
        console.log('Showing face-down card with image:', img.src);
        cardDiv.appendChild(img);
    } else {
        const img = document.createElement('img');
        const imagePath = getCardImagePath(card);
        img.src = imagePath;
        console.log('Showing face-up card with image:', imagePath, 'Card data:', card);
        img.onerror = function() {
            // Fallback if image not found
            console.error('Card image not found:', card, 'Path was:', imagePath);
            this.src = `${BASE_URL}/card_back.png`;
        };
        cardDiv.appendChild(img);
    }
    
    container.appendChild(cardDiv);
}

function clearCards(container) {
    container.innerHTML = '';
}

function updateGameDisplay() {
    chipCount.textContent = gameState.chips;
    betAmount.textContent = gameState.currentBet;
    
    if (gameState.playerScore > 0) {
        playerScore.textContent = gameState.playerScore;
        playerScore.style.display = 'inline-block';
    } else {
        playerScore.style.display = 'none';
    }
    
    if (gameState.dealerScore > 0 && gameState.gamePhase !== 'playing') {
        dealerScore.textContent = gameState.dealerScore;
        dealerScore.style.display = 'inline-block';
    } else if (gameState.dealerHand.length > 0) {
        // Show only visible card score during play
        const visibleScore = gameState.dealerHand[0] ? 
            (gameState.dealerHand[0].rank === 'ace' ? 11 : gameState.dealerHand[0].value || 10) : 0;
        dealerScore.textContent = visibleScore + ' + ?';
        dealerScore.style.display = 'inline-block';
    } else {
        dealerScore.style.display = 'none';
    }
}

function showResult(message, duration = 3000) {
    resultMessage.textContent = message;
    resultMessage.classList.add('show');
    
    setTimeout(() => {
        resultMessage.classList.remove('show');
    }, duration);
}

function handleUserEvent(params) {
    console.log('Handling user event:', params);
    
    // The event data structure can vary - sometimes it's params.event, sometimes it's direct
    let eventData = params;
    
    // If params has an event property, use that
    if (params && params.event) {
        eventData = params.event;
    }
    
    if (!eventData || !eventData.type) {
        console.log('No valid event data found in:', params);
        return;
    }
    
    switch(eventData.type) {
        case 'clear_table':
            // Clear the table for a new hand
            clearCards(playerCards);
            clearCards(dealerCards);
            gameState.playerHand = [];
            gameState.dealerHand = [];
            gameState.playerScore = 0;
            gameState.dealerScore = 0;
            gameState.chips = eventData.chips;
            gameState.gamePhase = 'betting';
            updateGameDisplay();
            gameActions.style.display = 'none';
            logEvent('Table cleared for new hand', { chips: eventData.chips }, true);
            break;
            
        case 'bet_placed':
            gameState.currentBet = eventData.amount;
            gameState.chips = eventData.remaining_chips;
            updateGameDisplay();
            logEvent('Bet placed', { amount: eventData.amount }, true);
            break;
            
        case 'cards_dealt':
            clearCards(playerCards);
            clearCards(dealerCards);
            
            console.log('Cards dealt event received:', eventData);
            console.log('Player hand:', eventData.player_hand);
            console.log('Dealer hand:', eventData.dealer_hand);
            
            gameState.playerHand = eventData.player_hand;
            gameState.dealerHand = eventData.dealer_hand;
            gameState.playerScore = eventData.player_score;
            gameState.gamePhase = 'playing';
            
            // Display player cards
            eventData.player_hand.forEach((card, index) => {
                console.log(`Displaying player card ${index}:`, card);
                displayCard(playerCards, card);
            });
            
            // Display dealer cards (one face up, one face down)
            console.log('Displaying dealer first card:', eventData.dealer_hand[0]);
            displayCard(dealerCards, eventData.dealer_hand[0]);
            console.log('Displaying dealer hole card (face down)');
            displayCard(dealerCards, null, true); // Face-down card
            
            updateGameDisplay();
            
            // Show action buttons if not blackjack
            if (gameState.playerScore !== 21) {
                gameActions.style.display = 'flex';
            }
            
            logEvent('Cards dealt', { 
                playerScore: eventData.player_score,
                dealerVisible: eventData.dealer_visible_score 
            }, true);
            
            if (gameState.playerScore === 21) {
                showResult('BLACKJACK!');
            }
            break;
            
        case 'player_hit':
            // Clear and redraw all cards to ensure sync
            clearCards(playerCards);
            
            // Update the game state with the full hand from server
            if (eventData.player_hand) {
                gameState.playerHand = eventData.player_hand;
                // Redraw all cards from the authoritative server state
                eventData.player_hand.forEach((card, index) => {
                    console.log(`Redrawing player card ${index} after hit:`, card);
                    displayCard(playerCards, card);
                });
            } else {
                // Fallback to just adding the new card if full hand not provided
                displayCard(playerCards, eventData.new_card);
            }
            
            gameState.playerScore = eventData.player_score;
            updateGameDisplay();
            
            if (eventData.busted) {
                gameActions.style.display = 'none';
                showResult('BUST!');
            }
            
            logEvent('Player hit', { 
                newCard: eventData.new_card.rank + ' of ' + eventData.new_card.suit,
                score: eventData.player_score,
                busted: eventData.busted 
            }, true);
            break;
            
        case 'player_stand':
            gameActions.style.display = 'none';
            logEvent('Player stands', { score: eventData.player_score }, true);
            break;
            
        case 'double_down':
            displayCard(playerCards, eventData.new_card);
            gameState.playerScore = eventData.player_score;
            gameState.currentBet = eventData.new_bet;
            gameState.chips = eventData.remaining_chips;
            gameActions.style.display = 'none';
            updateGameDisplay();
            
            logEvent('Double down', { 
                newBet: eventData.new_bet,
                score: eventData.player_score 
            }, true);
            break;
            
        case 'dealer_play':
            // Clear and redraw dealer cards (reveal hole card)
            clearCards(dealerCards);
            eventData.dealer_hand.forEach(card => {
                displayCard(dealerCards, card);
            });
            
            gameState.dealerScore = eventData.dealer_score;
            gameState.gamePhase = 'dealer_playing';  // Change phase so score shows
            updateGameDisplay();
            
            if (eventData.dealer_busted) {
                showResult('DEALER BUSTS!');
            }
            
            logEvent('Dealer plays', { 
                score: eventData.dealer_score,
                busted: eventData.dealer_busted 
            }, true);
            break;
            
        case 'hand_resolved':
            gameState.chips = eventData.total_chips;
            updateGameDisplay();
            
            showResult(eventData.result, 5000);
            
            // Hide action buttons
            gameActions.style.display = 'none';
            
            logEvent('Hand resolved', { 
                result: eventData.result,
                winnings: eventData.winnings,
                totalChips: eventData.total_chips 
            }, true);
            break;
            
        case 'game_reset':
            clearCards(playerCards);
            clearCards(dealerCards);
            gameState = {
                playerHand: [],
                dealerHand: [],
                playerScore: 0,
                dealerScore: 0,
                chips: eventData.chips,
                currentBet: 0,
                gamePhase: 'betting'
            };
            updateGameDisplay();
            gameActions.style.display = 'none';
            
            logEvent('New hand ready', { chips: eventData.chips }, true);
            break;
    }
}

// Voice commands are handled by the AI agent directly
// No UI buttons needed for game actions

// Connect to call with static token
async function connectToCall() {
    try {
        eventEntries.innerHTML = '';
        logEvent('Starting new connection...');
        
        if (!STATIC_TOKEN || STATIC_TOKEN === 'YOUR_SIGNALWIRE_TOKEN_HERE') {
            throw new Error('Please update STATIC_TOKEN with your actual SignalWire token');
        }
        
        statusDiv.textContent = 'Initializing client...';
        logEvent('Using static token', { tokenLength: STATIC_TOKEN.length });

        // Initialize client with debug options
        // SignalWire should be available on window when using UMD build
        const SignalWireSDK = window.SignalWire || SignalWire;
        logEvent('SignalWire SDK check', { 
            hasWindow: typeof window !== 'undefined',
            hasSignalWire: typeof SignalWire !== 'undefined',
            hasWindowSignalWire: typeof window.SignalWire !== 'undefined',
            SignalWireType: typeof SignalWireSDK,
            SignalWireKeys: SignalWireSDK ? Object.keys(SignalWireSDK) : []
        });

        // Based on the keys, we need to use Fabric
        if (typeof SignalWireSDK.Fabric === 'function') {
            client = await SignalWireSDK.Fabric({
                token: STATIC_TOKEN,
                logLevel: 'debug',
                debug: { logWsTraffic: false }
            });
        } else if (typeof SignalWireSDK.SignalWire === 'function') {
            client = await SignalWireSDK.SignalWire({
                token: STATIC_TOKEN,
                logLevel: 'debug',
                debug: { logWsTraffic: false }
            });
        } else {
            throw new Error('SignalWire SDK not found or not a function');
        }

        logEvent('Client initialized successfully');

        // Subscribe to ALL events on the client to debug
        const originalEmit = client.emit;
        client.emit = function(event, ...args) {
            if (event !== 'signalwire.socket.message' && event !== 'signalwire.socket.open') {
                logEvent(`Client event: ${event}`, args[0]);
            }
            return originalEmit.apply(this, [event, ...args]);
        };
        
        // Client-level disconnect handling
        client.on('signalwire.disconnect', (params) => {
            logEvent('Client disconnected', params);
            handleDisconnect();
        });
        
        client.on('signalwire.error', (params) => {
            logEvent('Client error', params);
            if (params && params.error && params.error.includes('disconnect')) {
                handleDisconnect();
            }
        });

        // Try multiple event patterns for user events
        client.on('user_event', (params) => {
            console.log('🎲 CLIENT EVENT: user_event (no prefix)', params);
            logEvent('user_event (no prefix)', params, true);
            handleUserEvent(params);
        });

        client.on('calling.user_event', (params) => {
            console.log('🎰 CLIENT EVENT: calling.user_event', params);
            logEvent('calling.user_event', params, true);
            handleUserEvent(params);
        });

        client.on('signalwire.event', (params) => {
            console.log('🃏 CLIENT EVENT: signalwire.event', params);
            if (params.event_type === 'user_event') {
                console.log('✅ Found user_event in signalwire.event!', params.params);
                logEvent('Found user_event in signalwire.event', params.params, true);
                handleUserEvent(params.params || params);
            } else {
                logEvent('signalwire.event', params);
            }
        });

        statusDiv.textContent = 'Getting media devices...';

        // Try to enumerate devices and select defaults
        try {
            // First, get permission to access devices by creating a temp stream
            const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
            tempStream.getTracks().forEach(track => track.stop()); // Stop the temp stream
            
            // Now enumerate devices with labels
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter(d => d.kind === 'audioinput');
            const videoInputs = devices.filter(d => d.kind === 'videoinput');
            
            // Find the default devices
            let audioDeviceId = undefined;
            let videoDeviceId = undefined;
            
            // Look for devices with "Default" in the label first
            const defaultAudio = audioInputs.find(d => d.label.toLowerCase().includes('default'));
            const defaultVideo = videoInputs.find(d => d.label.toLowerCase().includes('default'));
            
            if (defaultAudio) {
                audioDeviceId = defaultAudio.deviceId;
                logEvent('Found default audio device', { label: defaultAudio.label, deviceId: defaultAudio.deviceId });
            } else if (audioInputs.length > 0) {
                audioDeviceId = audioInputs[0].deviceId;
                logEvent('Using first audio device', { label: audioInputs[0].label, deviceId: audioInputs[0].deviceId });
            }
            
            if (defaultVideo) {
                videoDeviceId = defaultVideo.deviceId;
                logEvent('Found default video device', { label: defaultVideo.label, deviceId: defaultVideo.deviceId });
            } else if (videoInputs.length > 0) {
                videoDeviceId = videoInputs[0].deviceId;
                logEvent('Using first video device', { label: videoInputs[0].label, deviceId: videoInputs[0].deviceId });
            }
            
            statusDiv.textContent = 'Dialing...';
            
            // Dial into the room with specific devices
            logEvent('About to call client.dial with params', {
                to: DESTINATION,
                hasRootElement: !!document.getElementById('video-container'),
                audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true,
                video: videoDeviceId ? { deviceId: { exact: videoDeviceId } } : true,
                extension: 'sigmond_blackjack'
            });
            
            roomSession = await client.dial({
                to: DESTINATION,
                rootElement: document.getElementById('video-container'),
                audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true,
                video: videoDeviceId ? { deviceId: { exact: videoDeviceId } } : true,
                negotiateVideo: true,
                userVariables: {
                    userName: 'Blackjack Player',
                    interface: 'raw-sdk-static',
                    timestamp: new Date().toISOString(),
                    extension: 'sigmond_blackjack'
                }
            });
        } catch (error) {
            logEvent('Error getting devices', { error: error.message });
            statusDiv.textContent = 'Dialing with browser defaults...';
            
            // Fallback to letting browser choose
            roomSession = await client.dial({
                to: DESTINATION,
                rootElement: document.getElementById('video-container'),
                audio: true,
                video: true,
                negotiateVideo: true,
                userVariables: {
                    userName: 'Blackjack Player',
                    interface: 'raw-sdk-static',
                    timestamp: new Date().toISOString(),
                    extension: 'sigmond_blackjack'
                }
            });
        }

        logEvent('Dial initiated');

        // Subscribe to room session events
        roomSession.on('room.started', (params) => {
            logEvent('room.started', params);
        });

        roomSession.on('call.joined', (params) => {
            logEvent('call.joined', params);
            statusDiv.textContent = 'Connected to Dealer';
            connectBtn.style.display = 'none';
            hangupBtn.style.display = 'inline-block';
            muteBtn.style.display = 'inline-block';
            
            // Add connected class to shrink controls on mobile
            const controls = document.querySelector('.controls');
            if (controls) {
                controls.classList.add('connected');
            }
            
            // Make buttons ultra compact on mobile
            if (window.innerWidth <= 768) {
                hangupBtn.textContent = '✕';
                muteBtn.textContent = '🔇';
            }
            
            // Log audio output device
            const videoElement = document.querySelector('#video-container video');
            if (videoElement && typeof videoElement.setSinkId === 'function') {
                navigator.mediaDevices.enumerateDevices()
                    .then(devices => {
                        const audioOutputs = devices.filter(device => device.kind === 'audiooutput');
                        const currentOutput = audioOutputs.find(device => device.deviceId === videoElement.sinkId);
                        
                        logEvent('Audio output device', {
                            count: audioOutputs.length,
                            currentDevice: currentOutput ? currentOutput.label : 'System Default',
                            sinkId: videoElement.sinkId || 'default'
                        });
                    });
            }
        });
        
        // Watch for when localStream becomes available
        const checkLocalStream = setInterval(() => {
            if (roomSession && roomSession.localStream) {
                clearInterval(checkLocalStream);
                logEvent('Local stream found');
                
                const audioTracks = roomSession.localStream.getAudioTracks();
                const videoTracks = roomSession.localStream.getVideoTracks();
                
                // Log video device being used
                videoTracks.forEach(track => {
                    const settings = track.getSettings();
                    logEvent('Video input device', {
                        label: track.label,
                        deviceId: settings.deviceId,
                        width: settings.width,
                        height: settings.height,
                        frameRate: settings.frameRate
                    });
                });
                
                // Disable AGC and noise suppression on audio tracks
                audioTracks.forEach(track => {
                    // Log the audio device being used
                    const settings = track.getSettings();
                    
                    // Get device info to show if it's the default
                    navigator.mediaDevices.enumerateDevices().then(devices => {
                        const audioInputs = devices.filter(d => d.kind === 'audioinput');
                        const currentDevice = audioInputs.find(d => d.deviceId === settings.deviceId);
                        const isDefault = settings.deviceId === 'default' || 
                                        (currentDevice && currentDevice.deviceId === 'default');
                        
                        logEvent('Audio input device', {
                            label: track.label,
                            deviceId: settings.deviceId,
                            isSystemDefault: isDefault,
                            groupId: settings.groupId,
                            sampleRate: settings.sampleRate,
                            channelCount: settings.channelCount
                        });
                    });
                    
                    // Apply constraints to disable AGC and noise suppression
                    track.applyConstraints({
                        autoGainControl: false,
                        echoCancellation: true,
                        noiseSuppression: false
                    }).then(() => {
                        logEvent(`Disabled AGC and noise suppression on audio track: ${track.label}`);
                    }).catch(err => {
                        logEvent(`Failed to disable AGC/noise suppression: ${err.message}`);
                    });
                });
                
                // Check if we should start muted
                if (startMutedCheckbox.checked) {
                    audioTracks.forEach(track => {
                        track.enabled = false;
                        logEvent(`Muted audio track: ${track.label}`);
                    });
                    isMuted = true;
                    muteBtn.textContent = 'Unmute';
                    logEvent('Started call muted as requested');
                }
            }
        }, 50); // Check every 50ms
        
        // Store interval for cleanup
        roomSession._streamCheckInterval = checkLocalStream;
        
        roomSession.on('member.joined', (params) => {
            logEvent('member.joined', params);
        });
        
        roomSession.on('member.left', (params) => {
            logEvent('member.left', params);
        });
        
        roomSession.on('room.left', (params) => {
            logEvent('room.left', params);
            handleDisconnect();
        });
        
        roomSession.on('destroy', (params) => {
            logEvent('destroy', params);
            handleDisconnect();
        });
        
        roomSession.on('call.ended', (params) => {
            logEvent('call.ended', params);
            handleDisconnect();
        });
        
        roomSession.on('room.ended', (params) => {
            logEvent('room.ended', params);
            handleDisconnect();
        });
        
        roomSession.on('disconnected', (params) => {
            logEvent('disconnected', params);
            handleDisconnect();
        });
        
        roomSession.on('call.state', (params) => {
            logEvent('call.state', { state: params.state });
            // You might see states like 'new', 'trying', 'early', 'ringing', 'answered', 'ending', 'ended'
        });
        
        roomSession.on('session.ended', (params) => {
            logEvent('session.ended', params);
            handleDisconnect();
        });
        
        roomSession.on('member.updated', (params) => {
            logEvent('member.updated', params);
        });
        
        // Note: The tarot app has this commented out, but let's try it
        // roomSession.on('user_event', (params) => {
        //     console.log('Room session user_event:', params);
        //     handleUserEvent(params);
        // });

        // Start the call - this needs to be AFTER all event listeners are set up
        logEvent('Starting call...');
        await roomSession.start();

    } catch (error) {
        logEvent('Connection error', { error: error.message });
        statusDiv.textContent = 'Connection failed';
        console.error('Connection error:', error);
        connectBtn.style.display = 'inline-block';
        hangupBtn.style.display = 'none';
        muteBtn.style.display = 'none';
    }
}

function handleDisconnect() {
    // Clean up stream check interval
    if (roomSession && roomSession._streamCheckInterval) {
        clearInterval(roomSession._streamCheckInterval);
    }
    
    statusDiv.textContent = 'Disconnected';
    connectBtn.style.display = 'inline-block';
    hangupBtn.style.display = 'none';
    muteBtn.style.display = 'none';
    muteBtn.textContent = 'Mute';
    isMuted = false;
    gameActions.style.display = 'none';
    
    // Remove connected class to restore normal size
    const controls = document.querySelector('.controls');
    if (controls) {
        controls.classList.remove('connected');
    }
    
    // Restore button text
    hangupBtn.textContent = 'Leave';
    muteBtn.textContent = 'Mute';
    
    // Clear the game board
    clearCards(playerCards);
    clearCards(dealerCards);
    
    // Reset game state
    gameState = {
        playerHand: [],
        dealerHand: [],
        playerScore: 0,
        dealerScore: 0,
        chips: 1000,
        currentBet: 0,
        gamePhase: 'waiting'
    };
    updateGameDisplay();
    
    // Hide scores
    playerScore.style.display = 'none';
    dealerScore.style.display = 'none';
    
    // Clear any result message
    const resultMessage = document.getElementById('resultMessage');
    if (resultMessage) {
        resultMessage.classList.remove('show');
    }
    
    // Clean up video element created by SignalWire SDK
    const videoContainer = document.getElementById('video-container');
    if (videoContainer) {
        // Remove all child elements (video/audio elements)
        while (videoContainer.firstChild) {
            videoContainer.removeChild(videoContainer.firstChild);
        }
    }
    
    if (roomSession) {
        roomSession = null;
    }
    
    if (client) {
        client.disconnect();
        client = null;
    }
}

async function hangup() {
    if (roomSession) {
        try {
            await roomSession.hangup();
        } catch (e) {
            logEvent('Hangup error', { error: e.message });
        }
    }
    handleDisconnect();
}

function toggleMute() {
    try {
        // The localStream should be stored on the roomSession
        if (roomSession && roomSession.localStream) {
            const audioTracks = roomSession.localStream.getAudioTracks();
            
            // Toggle each audio track
            audioTracks.forEach(track => {
                track.enabled = !track.enabled;
                logEvent(`Audio track ${track.label} enabled: ${track.enabled}`);
            });
            
            // Update UI based on first track state
            if (audioTracks.length > 0) {
                isMuted = !audioTracks[0].enabled;
                if (window.innerWidth <= 768 && document.querySelector('.controls.connected')) {
                    muteBtn.textContent = isMuted ? '🔊' : '🔇';
                } else {
                    muteBtn.textContent = isMuted ? 'Unmute' : 'Mute';
                }
                logEvent(isMuted ? 'Microphone muted' : 'Microphone unmuted');
            }
        } else {
            logEvent('No local stream found on roomSession');
        }
    } catch (error) {
        logEvent('Mute toggle error', { error: error.message });
    }
}

// Event listeners
connectBtn.addEventListener('click', connectToCall);
hangupBtn.addEventListener('click', hangup);
muteBtn.addEventListener('click', toggleMute);

showLogCheckbox.addEventListener('change', (e) => {
    if (e.target.checked) {
        eventLog.classList.add('active');
    } else {
        eventLog.classList.remove('active');
    }
});

eventLogHeader.addEventListener('click', () => {
    const entries = document.getElementById('event-entries');
    if (entries.style.display === 'none') {
        entries.style.display = 'block';
        eventLogHeader.querySelector('span:last-child').textContent = '▼';
    } else {
        entries.style.display = 'none';
        eventLogHeader.querySelector('span:last-child').textContent = '▶';
    }
});

// Initialize on page load
window.addEventListener('load', () => {
    logEvent('Page loaded, ready to connect');
    updateGameDisplay();
});
