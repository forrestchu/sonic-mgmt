from kafka import KafkaConsumer
from kafka import TopicPartition
import json
import time

def kafka_consumer():
    
    file_prefix = "/var/spytest/"
    file_mapping = {
        'openbmp.parsed.collector':'kafka_collector',
        'openbmp.parsed.router':'kafka_router',
        'openbmp.parsed.peer':'kafka_peer',
        'openbmp.parsed.base_attribute':'kafka_baseattr',
        'openbmp.parsed.unicast_prefix':'kafka_unicast_prefix',
        'openbmp.parsed.l3vpn':'kafka_l3vpn',
        'openbmp.parsed.evpn':'kafka_evpn',
        'openbmp.parsed.ls_node':'kafka_lsnode',
        'openbmp.parsed.ls_link':'kafka_lslink',
        'openbmp.parsed.ls_prefix':'kafka_lsprefix',
        'openbmp.parsed.bmp_stat':'kafka_bmpstat',
        'openbmp.bmp_raw':'kafka_bmp_raw'
    }   

    consumer = KafkaConsumer(
                            bootstrap_servers=['192.0.0.250:9092'],
                            auto_offset_reset='earliest', 
                            group_id='dev')

    print("consumer...")
    print(consumer.bootstrap_connected())
    
    #topic_name = 'openbmp.parsed.peer'

    print(consumer.subscription())
    print(consumer.topics())
    
    #print(consumer.partitions_for_topic(topic_name))
    
    print(consumer.assignment())
    
    topic_part = []
    for t in consumer.topics():
        topic_part.append(TopicPartition(t, 0))

    consumer.assign(topic_part)
    
    print(consumer.assignment())
    # print(consumer.position(topic_part))

    for topic_partition in consumer.assignment():
        offset = consumer.position(topic_partition)
        print ("partition: %d, offset: %d" % (topic_partition.partition, offset))

    for msg in consumer:
        # print ("topic:%s, partition:%d, offset:%d: key=%s value=%s" % (msg.topic, msg.partition, msg.offset, msg.key, msg.value))
        
        topic = msg.topic
        value = msg.value.decode("utf-8")
        with open(file_prefix+file_mapping.get(topic),'a') as f:
            f.write(value)

if __name__ == '__main__':
    kafka_consumer()