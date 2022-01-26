/*
    Last.fm Music Analyzer
    Copyright (C) 2022, H. Kamran

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.
*/

require("dotenv").config();

const { Client, Intents, MessageEmbed, DMChannel } = require("discord.js");
const { existsSync, writeFileSync, readFileSync, stat } = require("fs");
const { unlink } = require("fs/promises");
const { exec } = require("child_process");

const token = process.env.DISCORD_TOKEN;

// Create a new client instance
const client = new Client({ intents: [Intents.FLAGS.GUILDS] });

const timeframeOptions = [
    { label: "Today", value: "today" },
    { label: "This week", value: "this_week" },
    { label: "This month", value: "this_month" },
    { label: "This year", value: "this_year" },
    { label: "Yesterday", value: "yesterday" },
    {
        label: "Last week",
        value: "last_week",
    },
    { label: "Last month", value: "last_month" },
    { label: "Last year", value: "last_year" },
];
const getLastfmUsername = (userId) => {
    const path = "./users.json";

    if (existsSync(path)) {
        const currentUsers = JSON.parse(readFileSync(path));
        if (currentUsers.hasOwnProperty(userId)) {
            return currentUsers[userId];
        } else {
            return null;
        }
    } else {
        return null;
    }
};
const capitalizeFirstLetter = (string) =>
    string.charAt(0).toUpperCase() + string.slice(1);

const titleCase = (string) =>
    string
        .split(" ")
        .map((w) => w[0].toUpperCase() + w.substr(1).toLowerCase())
        .join(" ");
const postAnalysis = (
    commandName,
    isMessageDM,
    label,
    lastfmUsername,
    interaction,
    envVars,
    startTime,
    execError,
    stderr
) => {
    if (execError) {
        console.error(
            `[${new Date().getTime()}] ${capitalizeFirstLetter(
                commandName.replace("get-", "").replace("-", " ")
            )} retrieval for ${
                label.toLowerCase().indexOf("last") > -1 ? "the " : ""
            }${label.toLowerCase()} failed`
        );
        console.error(execError);

        if (
            stderr.indexOf("TypeError: string indices must be integers") !== -1
        ) {
            console.log("Deleting cached responses and restarting...");

            unlink(`../analyzer/analyzer_lastfm_user_${lastfmUsername}.sqlite`);

            console.log(
                existsSync(
                    `../analyzer/analyzer_lastfm_user_${lastfmUsername}.sqlite`
                )
            );

            exec(
                "cd ../analyzer; $(which python3) lastfm_analysis.py",
                {
                    env: envVars,
                },
                // eslint-disable-next-line no-unused-vars
                (execError, _, stderr) =>
                    postAnalysis(
                        commandName,
                        isMessageDM,
                        label,
                        lastfmUsername,
                        interaction,
                        envVars,
                        startTime,
                        execError,
                        stderr
                    )
            );
        }

        interaction.followUp({
            embeds: [
                new MessageEmbed()
                    .setColor("#FF0000")
                    .setTitle(`Music Analysis for ${titleCase(label)}`)
                    .setDescription(
                        `An error occurred when fetching ${
                            label.toLowerCase().indexOf("last") > -1
                                ? "the "
                                : ""
                        }${label.toLowerCase()}'s statistics`
                    ),
            ],
            ephemeral: !isMessageDM,
        });

        return;
    }

    stat(`../analyzer/user_output_${lastfmUsername}.json`, (error, stats) => {
        if (!error) {
            if (stats.mtime.getTime() > startTime) {
                console.log(
                    `[${stats.mtime.getTime()}] ${capitalizeFirstLetter(
                        commandName.replace("get-", "").replace("-", " ")
                    )} retrieval for ${
                        label.toLowerCase().indexOf("last") > -1 ? "the " : ""
                    }${label.toLowerCase()} completed`
                );

                const user_output = JSON.parse(
                    readFileSync(
                        `../analyzer/user_output_${lastfmUsername}.json`
                    )
                );

                let message = null;
                if (commandName === "get-all-stats") {
                    message = `${user_output["tracks"]} (${user_output[
                        "duration"
                    ].replace("You listened for ", "")}).\n\n${
                        user_output["toptrack"]
                    }\n${user_output["topartist"]}\n${user_output["topalbum"]}`;
                } else if (commandName === "get-top-tracks") {
                    message = user_output["toptrack"];
                } else if (commandName === "get-top-artists") {
                    message = user_output["topartist"];
                } else if (commandName === "get-top-albums") {
                    message = user_output["topalbum"];
                } else if (commandName === "get-duration") {
                    message = user_output["duration"];
                } else if (commandName === "get-track-count") {
                    message = user_output["tracks"];
                }

                interaction.user.send({
                    embeds: [
                        new MessageEmbed()
                            .setColor("#F472B6")
                            .setTitle(`Music Analysis for ${titleCase(label)}`)
                            .setDescription(message),
                    ],
                });
                if (!isMessageDM) {
                    interaction.followUp({
                        embeds: [
                            new MessageEmbed()
                                .setColor("#F472B6")
                                .setTitle(
                                    `Music Analysis for ${titleCase(label)}`
                                )
                                .setDescription(message),
                        ],
                        ephemeral: !isMessageDM,
                    });
                }
            }
        }
    });
};

// When the client is ready, run this code (only once)
client.once("ready", () => {
    console.log("Ready to respond!");
    client.user.setActivity("Analyzing statistics!", { type: "COMPETING" });
});

// When the client is added to a new server/guild, run this code
client.on("guildCreate", (guild) => {
    client.channels.cache
        .get(guild.systemChannelId)
        .send(
            `Hello users of ${guild.name}! I am Music Analyzer, a bot that is powered by Last.fm to retrieve your statistics at any time! I'm basically Spotify Wrapped, but year-round!\n\nTo begin, go into any channel and type \`set-lastfm-username\` and pass your Last.fm username. Then, use any of the commands provided by me! All output will only be seen by you, no one else can see it.\n\nSo go ahead, enjoy the power of **MUSIC ANALYZER**!`
        );
});

client.on("interactionCreate", async (interaction) => {
    if (!interaction.isCommand()) return;
    const { commandName } = interaction;
    const isMessageDM = interaction.channel instanceof DMChannel;

    if (commandName === "set-lastfm-username") {
        const username = interaction.options.getString("username");
        const path = "./users.json";

        if (existsSync(path)) {
            const currentUsers = Object.entries(JSON.parse(readFileSync(path)));
            if (
                !Object.fromEntries(currentUsers).hasOwnProperty(
                    interaction.user.id
                )
            ) {
                currentUsers.push([interaction.user.id, username]);
                writeFileSync(
                    path,
                    JSON.stringify(Object.fromEntries(currentUsers))
                );

                await interaction.reply({
                    content: "Username saved!",
                    ephemeral: !isMessageDM,
                });
            } else {
                await interaction.reply({
                    content: "Your username was already saved.",
                    ephemeral: !isMessageDM,
                });
            }
        } else {
            writeFileSync(
                path,
                JSON.stringify(
                    Object.fromEntries([[interaction.user.id, username]])
                )
            );

            await interaction.reply({
                content: "Username saved!",
                ephemeral: !isMessageDM,
            });
        }
    } else if (
        [
            "get-all-stats",
            "get-top-tracks",
            "get-top-artists",
            "get-top-albums",
            "get-duration",
            "get-track-count",
        ].indexOf(commandName) !== -1
    ) {
        const lastfmUsername = getLastfmUsername(interaction.user.id);
        if (!lastfmUsername) {
            await interaction.reply({
                embeds: [
                    new MessageEmbed()
                        .setColor("#FF0000")
                        .setTitle("Music Analysis")
                        .setDescription(
                            "Please set your Last.fm username with the `set-lastfm-username` command before getting any statistics!"
                        ),
                ],
                components: [],
                ephemeral: !isMessageDM,
            });
        } else {
            const value = interaction.options.getString("timeframe");
            const label = timeframeOptions.filter(
                (option) => option.value === value
            )[0].label;

            await interaction.reply({
                embeds: [
                    new MessageEmbed()
                        .setColor("#F472B6")
                        .setTitle("Music Analysis")
                        .setDescription(
                            `Getting the statistics for ${
                                label.toLowerCase().indexOf("last") > -1
                                    ? "the "
                                    : ""
                            }${label.toLowerCase()}!\n\nThis may take some time. You will be notified when the analysis is completed, assuming you have mention notifications on.\n\nPlease note that the duration provided may not be the actual duration you've listened to, due to issues with the way Last.fm provides data. Attempts have been taken to circumvent those issues, but nevertheless, some tracks do not have durations.`
                        ),
                ],
                ephemeral: !isMessageDM,
            });

            const envVars = Object.fromEntries(
                readFileSync("../analyzer/.env")
                    .toString()
                    .split("\n")
                    .map((variable) => variable.split("="))
            );
            envVars["USERNAME"] = lastfmUsername;
            envVars["TIMEFRAME"] = value.toUpperCase();

            const finalEnvVars = Object.assign({}, process.env, envVars);

            const startTime = new Date().getTime();

            console.log(
                `[${startTime}] Beginning ${commandName
                    .replace("get-", "")
                    .replace("-", " ")} retrieval for ${
                    label.toLowerCase().indexOf("last") > -1 ? "the " : ""
                }${label.toLowerCase()}`
            );

            if (
                !existsSync(
                    `../analyzer/analyzer_lastfm_user_${lastfmUsername}.sqlite`
                )
            ) {
                console.log(`[${startTime}] Retrieving fresh statistics...`);

                interaction.followUp({
                    embeds: [
                        new MessageEmbed()
                            .setColor("#F472B6")
                            .setTitle(`Music Analysis for ${titleCase(label)}`)
                            .setDescription(
                                "Getting fresh results, this may take longer than expected"
                            ),
                    ],
                    ephemeral: !isMessageDM,
                });
            }

            exec(
                "cd ../analyzer; $(which python3) lastfm_analysis.py",
                {
                    env: finalEnvVars,
                },
                // eslint-disable-next-line no-unused-vars
                (execError, _, stderr) =>
                    postAnalysis(
                        commandName,
                        isMessageDM,
                        label,
                        lastfmUsername,
                        interaction,
                        finalEnvVars,
                        startTime,
                        execError,
                        stderr
                    )
            );
        }
    }
});

// Login to Discord with your client's token
client.login(token);
