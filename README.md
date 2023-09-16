# Discord2TerminalV2

##  What is it?

This is a rewrite of the original project, [Discord2Terminal](https://github.com/TheUntraceable/DiscordTerminal).
The reason for this rewrite is because that project was made with JS, and is a mess. I can't understand the code too well. I am more comfortable with Python, so I decided to rewrite it in Python. This is a separate repo to show the distinction between the two. The original project is still useable, but I will not be updating it anymore. One distinction between the two is that this one is Linux only, as it uses the Discord Unix Socket, which is only available on Linux. I know of there being a pipe on Windows, but it looks like a mess to implement, and I don't want to be switching in between machines. If there is a noticeable demand for a Windows version, I will make one, but I don't see that happening.

## QnA

### Why did you make this?

I was messing around with [DiscordRPC](https://github.com/DiscordJS/RPC). There is not much documentation on it, so I decided to just read the Discord API Docs directly, to see a more definite list of events, and commands I can send to the Unix Socket. This is when I realised that you receive all of the message events (CREATE, UPDATE, DELETE), and I noticed that the `author` attribute of the message payload had a `colour` attribute. I then realised that I had all the tools (excluding sending messages, but I have my workarounds 😉) to make my own Discord Client for the terminal, which would look very cool.

### Is this against Discord ToS?

No. There is no self-botting going on, you're the Discord Client's unix socket to read events, etc. If I were to make a self-bot, I would be using the Discord API, which is against the ToS. Sending messages is done using a webhook setup by the client. This is not against the ToS, as it is a webhook, and not a self-bot.

## Todo List

- Implement RPC Client
  - [x] Connecting to the socket
  - [x] "Logging in"
  - [x] Reading commands/events
  - [x] Sending commands/events
  - [ ] Handling errors
- Implement Discord Client
  - [x] Subscribing to events
  - [x] Reading events
  - [ ] Saving Data
- Implement Webhook API
  - [ ] Registering webhooks
  - [ ] Handling ratelimits
  - [ ] Ratelimiting users
  - [ ] Banning spammers
